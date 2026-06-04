"""Compare two captured versions of a commit (or "base") and produce a
per-file unified diff that the frontend can render with react-diff-view."""

from __future__ import annotations

import difflib
from dataclasses import dataclass

from sqlmodel import Session, select

from gitloco.models import CommitVersion, CommitVersionFile, Snapshot

BASE = "base"


@dataclass(frozen=True)
class _FileSide:
    """One side of a file at a given version: its path (which may be the old
    or new path depending on side) and its text content (or None if absent)."""

    path: str | None
    content: str | None
    is_binary: bool


@dataclass(frozen=True)
class CompareFile:
    file_path: str
    status: str  # "added" | "deleted" | "modified" | "renamed" | "unchanged" | "binary"
    is_binary: bool
    old_path: str | None
    new_path: str | None
    patch_text: str


def _read_snapshot_text(
    session: Session, snapshot_id: int | None
) -> tuple[str | None, bool]:
    if snapshot_id is None:
        return None, False
    snap = session.get(Snapshot, snapshot_id)
    if snap is None:
        return None, False
    if snap.is_binary:
        return None, True
    try:
        return snap.content.decode("utf-8", errors="replace"), False
    except Exception:
        return None, True


def _version_files(
    session: Session, version: CommitVersion
) -> list[CommitVersionFile]:
    return list(
        session.exec(
            select(CommitVersionFile)
            .where(CommitVersionFile.version_id == version.id)
            .order_by(CommitVersionFile.file_path)
        ).all()
    )


def _resolve_version(
    session: Session, sha: str, name: str
) -> CommitVersion | None:
    if name.lower() in (BASE,):
        return None
    if name.lower().startswith("v"):
        try:
            n = int(name[1:])
        except ValueError as exc:
            raise ValueError(f"invalid version name: {name}") from exc
    else:
        try:
            n = int(name)
        except ValueError as exc:
            raise ValueError(f"invalid version name: {name}") from exc
    v = session.exec(
        select(CommitVersion).where(
            CommitVersion.commit_sha == sha,
            CommitVersion.version_number == n,
        )
    ).first()
    if v is None:
        raise ValueError(f"commit {sha} has no version {n}")
    return v


def _build_path_map(
    files: list[CommitVersionFile],
) -> dict[str, CommitVersionFile]:
    return {f.file_path: f for f in files}


def _side_from_version_file(
    session: Session,
    file: CommitVersionFile | None,
    side: str,  # "parent" | "commit"
) -> _FileSide:
    if file is None:
        return _FileSide(path=None, content=None, is_binary=False)
    if side == "parent":
        text, is_binary = _read_snapshot_text(session, file.parent_snapshot_id)
        path = file.old_path
    else:
        text, is_binary = _read_snapshot_text(session, file.commit_snapshot_id)
        path = file.new_path
    return _FileSide(path=path, content=text, is_binary=is_binary)


def _unified_patch(
    *,
    file_path: str,
    from_side: _FileSide,
    to_side: _FileSide,
) -> CompareFile:
    """Render a unified-diff `patch_text` for the (from_side → to_side) pair
    in a shape compatible with our existing /diff endpoint."""
    if from_side.is_binary or to_side.is_binary:
        return CompareFile(
            file_path=file_path,
            status="binary",
            is_binary=True,
            old_path=from_side.path,
            new_path=to_side.path,
            patch_text="",
        )

    from_text = from_side.content or ""
    to_text = to_side.content or ""

    if from_side.content is None and to_side.content is None:
        return CompareFile(
            file_path=file_path,
            status="unchanged",
            is_binary=False,
            old_path=from_side.path,
            new_path=to_side.path,
            patch_text="",
        )

    from_present = from_side.content is not None
    to_present = to_side.content is not None

    if not from_present and to_present:
        status = "added"
        from_label = "/dev/null"
        to_label = f"b/{to_side.path or file_path}"
    elif from_present and not to_present:
        status = "deleted"
        from_label = f"a/{from_side.path or file_path}"
        to_label = "/dev/null"
    elif (from_side.path or file_path) != (to_side.path or file_path):
        status = "renamed"
        from_label = f"a/{from_side.path}"
        to_label = f"b/{to_side.path}"
    elif from_text == to_text:
        return CompareFile(
            file_path=file_path,
            status="unchanged",
            is_binary=False,
            old_path=from_side.path,
            new_path=to_side.path,
            patch_text="",
        )
    else:
        status = "modified"
        from_label = f"a/{from_side.path or file_path}"
        to_label = f"b/{to_side.path or file_path}"

    from_lines = from_text.splitlines(keepends=True)
    to_lines = to_text.splitlines(keepends=True)
    body_lines = list(
        difflib.unified_diff(
            from_lines,
            to_lines,
            fromfile=from_label,
            tofile=to_label,
            n=3,
        )
    )
    # Prepend a `diff --git` header so gitdiff-parser on the frontend recognizes
    # this as one file.
    header_old = from_side.path or file_path
    header_new = to_side.path or file_path
    full = "".join([f"diff --git a/{header_old} b/{header_new}\n", *body_lines])
    # Ensure the patch ends with a newline.
    if not full.endswith("\n"):
        full += "\n"
    return CompareFile(
        file_path=file_path,
        status=status,
        is_binary=False,
        old_path=from_side.path,
        new_path=to_side.path,
        patch_text=full,
    )


def compare_versions(
    session: Session,
    *,
    sha: str,
    from_name: str,
    to_name: str,
) -> tuple[list[CompareFile], CommitVersion | None, CommitVersion | None]:
    """Build a per-file unified diff between two version states.

    Names: ``"base"`` (the commit's parent state, from V_to's parent snapshots)
    or ``"V<n>"`` (V_to's / V_from's commit-side state at that version).
    """
    from_version = _resolve_version(session, sha, from_name)
    to_version = _resolve_version(session, sha, to_name)
    if to_version is None:
        # "to=base" doesn't really make sense — fall back to the latest version.
        latest = session.exec(
            select(CommitVersion)
            .where(CommitVersion.commit_sha == sha)
            .order_by(CommitVersion.version_number.desc())  # type: ignore[union-attr]
        ).first()
        to_version = latest
        if to_version is None:
            return [], from_version, None

    # If 'from' is "base", use parent snapshots from the 'to' version.
    # If 'from' is a version, use that version's commit_content.
    to_files = _version_files(session, to_version)
    to_map = _build_path_map(to_files)

    if from_version is None:
        # File set = to's file set; "from" is each file's parent_content.
        results: list[CompareFile] = []
        for path, f in to_map.items():
            from_side = _side_from_version_file(session, f, "parent")
            to_side = _side_from_version_file(session, f, "commit")
            results.append(
                _unified_patch(file_path=path, from_side=from_side, to_side=to_side)
            )
        return results, None, to_version

    from_files = _version_files(session, from_version)
    from_map = _build_path_map(from_files)

    all_paths = sorted(set(from_map.keys()) | set(to_map.keys()))
    results = []
    for path in all_paths:
        from_side = _side_from_version_file(session, from_map.get(path), "commit")
        to_side = _side_from_version_file(session, to_map.get(path), "commit")
        results.append(
            _unified_patch(file_path=path, from_side=from_side, to_side=to_side)
        )
    return results, from_version, to_version

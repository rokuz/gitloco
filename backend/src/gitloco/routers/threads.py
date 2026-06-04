from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Query, Request
from sqlmodel import Session, select

from gitloco import persistence as pc
from gitloco.models import CommitVersion, Reply, Thread
from gitloco.schemas import (
    CommitRewriteIn,
    CommitVersionDetailOut,
    CommitVersionFileOut,
    CommitVersionListItemOut,
    CompareFileOut,
    CompareOut,
    NewReplyIn,
    NewThreadIn,
    ReplyOut,
    ThreadOut,
)

router = APIRouter(prefix="/api/threads", tags=["threads"])

Author = Literal["human", "agent"]


def _author_from_header(value: str | None) -> Author:
    if value is None:
        return "human"
    v = value.strip().lower()
    if v in ("agent", "ai", "claude"):
        return "agent"
    return "human"


def _thread_out(thread: Thread) -> ThreadOut:
    return ThreadOut(
        id=thread.id,  # type: ignore[arg-type]
        commit_sha=thread.commit_hash,
        file_path=thread.file_path,
        line_side=thread.line_side,
        line_number=thread.line_number,
        status=thread.status,
        created_at=thread.created_at,
        resolved_at=thread.resolved_at,
        replies=[
            ReplyOut(
                id=r.id,  # type: ignore[arg-type]
                author=r.author,
                body=r.body,
                created_at=r.created_at,
            )
            for r in thread.replies
        ],
    )


@router.get("", response_model=list[ThreadOut])
def list_threads(
    request: Request,
    status: Literal["open", "resolved", "all"] = Query("all"),
    sha: str | None = Query(None),
    path: str | None = Query(None),
) -> list[ThreadOut]:
    engine = request.app.state.engine
    repo = request.app.state.repo
    with Session(engine) as session:
        if sha is not None:
            threads = pc.threads_for_hash(session, repo, sha)
        else:
            threads = list(session.exec(select(Thread).order_by(Thread.created_at)).all())
        session.commit()  # resolve_pc may have linked a rewritten hash
        out = []
        for t in threads:
            if status != "all" and t.status != status:
                continue
            if path is not None and t.file_path != path:
                continue
            out.append(_thread_out(t))
        return out


@router.get("/orphans", response_model=list[ThreadOut])
def list_orphan_threads(request: Request) -> list[ThreadOut]:
    """Threads whose persistent commit has no version reachable from HEAD, so
    they don't appear under any current commit. Surfaced so they can still be
    resolved."""
    engine = request.app.state.engine
    repo = request.app.state.repo
    with Session(engine) as session:
        return [_thread_out(t) for t in pc.orphaned_threads(session, repo)]


@router.get("/open-counts", response_model=dict[str, int])
def open_thread_counts(request: Request) -> dict[str, int]:
    """Open-thread count keyed by every commit hash that maps to a persistent
    commit, so the UI can badge whichever hash a commit row shows."""
    engine = request.app.state.engine
    with Session(engine) as session:
        open_by_pc: dict[int, int] = {}
        for t in session.exec(select(Thread).where(Thread.status == "open")).all():
            open_by_pc[t.persistent_commit_id] = (
                open_by_pc.get(t.persistent_commit_id, 0) + 1
            )
        counts: dict[str, int] = {}
        for v in session.exec(select(CommitVersion)).all():
            n = open_by_pc.get(v.persistent_commit_id, 0)
            if n:
                counts[v.commit_hash] = n
        return counts


@router.post("", response_model=ThreadOut, status_code=201)
def create_thread(
    payload: NewThreadIn,
    request: Request,
    x_gitloco_author: str | None = Header(default=None),
) -> ThreadOut:
    if not payload.body.strip():
        raise HTTPException(status_code=400, detail="body must not be empty")
    if _author_from_header(x_gitloco_author) != "human":
        raise HTTPException(
            status_code=403,
            detail="only humans may start new threads — agents reply only",
        )

    engine = request.app.state.engine
    repo = request.app.state.repo
    with Session(engine) as session:
        pc_id = pc.resolve_pc(session, repo, payload.commit_sha, create=True)
        thread = Thread(
            persistent_commit_id=pc_id,  # type: ignore[arg-type]
            commit_hash=payload.commit_sha,
            file_path=payload.file_path,
            line_side=payload.line_side,
            line_number=payload.line_number,
        )
        session.add(thread)
        session.flush()
        session.add(
            Reply(thread_id=thread.id, author="human", body=payload.body)  # type: ignore[arg-type]
        )
        session.commit()
        session.refresh(thread)
        return _thread_out(thread)


@router.post("/{thread_id}/replies", response_model=ThreadOut)
def reply_to_thread(
    thread_id: int,
    payload: NewReplyIn,
    request: Request,
    x_gitloco_author: str | None = Header(default=None),
) -> ThreadOut:
    if not payload.body.strip():
        raise HTTPException(status_code=400, detail="body must not be empty")
    author = _author_from_header(x_gitloco_author)
    engine = request.app.state.engine
    with Session(engine) as session:
        thread = session.get(Thread, thread_id)
        if thread is None:
            raise HTTPException(status_code=404, detail=f"thread {thread_id} not found")
        if thread.status == "resolved":
            raise HTTPException(
                status_code=409, detail="thread is resolved and cannot accept replies"
            )
        session.add(Reply(thread_id=thread_id, author=author, body=payload.body))
        session.commit()
        session.refresh(thread)
        return _thread_out(thread)


@router.post("/{thread_id}/resolve", response_model=ThreadOut)
def resolve_thread(
    thread_id: int,
    request: Request,
    x_gitloco_author: str | None = Header(default=None),
) -> ThreadOut:
    if _author_from_header(x_gitloco_author) != "human":
        raise HTTPException(status_code=403, detail="only humans may resolve threads")
    engine = request.app.state.engine
    with Session(engine) as session:
        thread = session.get(Thread, thread_id)
        if thread is None:
            raise HTTPException(status_code=404, detail=f"thread {thread_id} not found")
        if thread.status != "resolved":
            thread.status = "resolved"
            thread.resolved_at = datetime.now(UTC)
            session.add(thread)
            session.commit()
            session.refresh(thread)
        return _thread_out(thread)


# ---- Commit versions ---------------------------------------------------------

commit_versions_router = APIRouter(prefix="/api/commits", tags=["commit-versions"])


@commit_versions_router.post("/rewrites", status_code=200)
def record_commit_rewrite(payload: CommitRewriteIn, request: Request) -> dict:
    """Record that ``old_sha`` was rewritten to ``new_sha`` — appends new_sha as
    a version of old_sha's persistent commit so threads and version history
    follow the commit."""
    engine = request.app.state.engine
    repo = request.app.state.repo
    with Session(engine) as session:
        added = pc.record_rewrite(session, repo, payload.old_sha, payload.new_sha)
        session.commit()
    return {"linked": added}


def _short(h: str) -> str:
    return "WORKING" if h == "WORKING_TREE" else h[:7]


@commit_versions_router.get(
    "/{sha}/versions", response_model=list[CommitVersionListItemOut]
)
def list_commit_versions(sha: str, request: Request) -> list[CommitVersionListItemOut]:
    engine = request.app.state.engine
    repo = request.app.state.repo
    with Session(engine) as session:
        versions = pc.versions_for_hash(session, repo, sha)
        session.commit()
        return [
            CommitVersionListItemOut(
                version_number=v.version_number,
                commit_hash=v.commit_hash,
                short_hash=_short(v.commit_hash),
                subject=v.subject,
                created_at=v.created_at,
            )
            for v in versions
        ]


@commit_versions_router.get("/{sha}/compare", response_model=CompareOut)
def compare(
    sha: str,
    request: Request,
    from_: str = Query("base", alias="from"),
    to: str = Query("latest"),
) -> CompareOut:
    """Per-file unified diff between two versions of the commit. ``from``
    defaults to ``base`` (the parent state); ``to`` defaults to ``latest``."""
    engine = request.app.state.engine
    repo = request.app.state.repo
    with Session(engine) as session:
        try:
            result = pc.compare(session, repo, sha, from_, to)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        session.commit()
        return CompareOut(
            sha=sha,
            from_name=result["from_name"],
            to_name=result["to_name"],
            from_version_number=result["from_version"],
            to_version_number=result["to_version"],
            files=[CompareFileOut(**f) for f in result["files"]],
        )


@commit_versions_router.get(
    "/{sha}/versions/{n}", response_model=CommitVersionDetailOut
)
def get_commit_version(sha: str, n: int, request: Request) -> CommitVersionDetailOut:
    engine = request.app.state.engine
    repo = request.app.state.repo
    with Session(engine) as session:
        versions = pc.versions_for_hash(session, repo, sha)
        version = next((v for v in versions if v.version_number == n), None)
        if version is None:
            raise HTTPException(
                status_code=404, detail=f"commit {sha} has no version {n}"
            )
        files = pc._version_files(session, version)
        session.commit()
        return CommitVersionDetailOut(
            version_number=version.version_number,
            commit_hash=version.commit_hash,
            created_at=version.created_at,
            files=[
                CommitVersionFileOut(
                    file_path=f.file_path,
                    status=f.status,
                    old_path=f.old_path,
                    new_path=f.new_path,
                    parent_content=pc.snapshot_text(session, f.parent_snapshot_id),
                    commit_content=pc.snapshot_text(session, f.commit_snapshot_id),
                )
                for f in files.values()
            ],
        )

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Query, Request
from sqlmodel import Session, select

from gitloco.compare import compare_versions
from gitloco.models import (
    CommitVersion,
    CommitVersionFile,
    Reply,
    Thread,
)
from gitloco.schemas import (
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
from gitloco.snapshots import capture_version, snapshot_text

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
        commit_sha=thread.commit_sha,
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
    with Session(engine) as session:
        stmt = select(Thread)
        if status != "all":
            stmt = stmt.where(Thread.status == status)
        if sha is not None:
            stmt = stmt.where(Thread.commit_sha == sha)
        if path is not None:
            stmt = stmt.where(Thread.file_path == path)
        stmt = stmt.order_by(Thread.created_at)
        threads = session.exec(stmt).all()
        return [_thread_out(t) for t in threads]


@router.post("", response_model=ThreadOut, status_code=201)
def create_thread(
    payload: NewThreadIn,
    request: Request,
    x_gitloco_author: str | None = Header(default=None),
) -> ThreadOut:
    if not payload.body.strip():
        raise HTTPException(status_code=400, detail="body must not be empty")
    author = _author_from_header(x_gitloco_author)
    if author != "human":
        raise HTTPException(
            status_code=403,
            detail="only humans may start new threads — agents reply only",
        )

    engine = request.app.state.engine
    repo = request.app.state.repo
    with Session(engine) as session:
        thread = Thread(
            commit_sha=payload.commit_sha,
            file_path=payload.file_path,
            line_side=payload.line_side,
            line_number=payload.line_number,
        )
        session.add(thread)
        session.flush()

        _version, primary_parent, primary_commit = capture_version(
            repo=repo,
            session=session,
            commit_sha=payload.commit_sha,
            trigger="thread_created",
            triggering_thread_id=thread.id,
            triggering_reply_id=None,
            primary_file_path=payload.file_path,
        )
        thread.parent_snapshot_id = primary_parent.id if primary_parent else None
        thread.commit_snapshot_id = primary_commit.id if primary_commit else None
        session.add(thread)

        root_reply = Reply(
            thread_id=thread.id,  # type: ignore[arg-type]
            author="human",
            body=payload.body,
        )
        session.add(root_reply)
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
    repo = request.app.state.repo
    with Session(engine) as session:
        thread = session.get(Thread, thread_id)
        if thread is None:
            raise HTTPException(status_code=404, detail=f"thread {thread_id} not found")
        if thread.status == "resolved":
            raise HTTPException(
                status_code=409, detail="thread is resolved and cannot accept replies"
            )
        reply = Reply(thread_id=thread_id, author=author, body=payload.body)
        session.add(reply)
        session.flush()

        # Human replies trigger a new commit version capture. Agent replies do not.
        if author == "human":
            capture_version(
                repo=repo,
                session=session,
                commit_sha=thread.commit_sha,
                trigger="reply",
                triggering_thread_id=thread_id,
                triggering_reply_id=reply.id,
                primary_file_path=thread.file_path,
            )

        session.commit()
        session.refresh(thread)
        return _thread_out(thread)


@router.post("/{thread_id}/resolve", response_model=ThreadOut)
def resolve_thread(
    thread_id: int,
    request: Request,
    x_gitloco_author: str | None = Header(default=None),
) -> ThreadOut:
    author = _author_from_header(x_gitloco_author)
    if author != "human":
        raise HTTPException(status_code=403, detail="only humans may resolve threads")
    engine = request.app.state.engine
    with Session(engine) as session:
        thread = session.get(Thread, thread_id)
        if thread is None:
            raise HTTPException(status_code=404, detail=f"thread {thread_id} not found")
        if thread.status == "resolved":
            return _thread_out(thread)
        thread.status = "resolved"
        thread.resolved_at = datetime.now(UTC)
        session.add(thread)
        session.commit()
        session.refresh(thread)
        return _thread_out(thread)


# ---- Commit versions ---------------------------------------------------------

commit_versions_router = APIRouter(prefix="/api/commits", tags=["commit-versions"])


@commit_versions_router.get(
    "/{sha}/versions", response_model=list[CommitVersionListItemOut]
)
def list_commit_versions(sha: str, request: Request) -> list[CommitVersionListItemOut]:
    engine = request.app.state.engine
    with Session(engine) as session:
        rows = list(
            session.exec(
                select(CommitVersion)
                .where(CommitVersion.commit_sha == sha)
                .order_by(CommitVersion.version_number)
            ).all()
        )
        return [
            CommitVersionListItemOut(
                version_number=v.version_number,
                created_at=v.created_at,
                trigger=v.trigger,
                triggering_thread_id=v.triggering_thread_id,
                triggering_reply_id=v.triggering_reply_id,
            )
            for v in rows
        ]


@commit_versions_router.get("/{sha}/compare", response_model=CompareOut)
def compare(
    sha: str,
    request: Request,
    from_: str = Query("base", alias="from"),
    to: str = Query("latest"),
) -> CompareOut:
    """Compare two captured versions of a commit and return a per-file unified
    diff suitable for react-diff-view. ``from`` defaults to ``base`` (the
    commit's parent state). ``to`` defaults to ``latest`` (most recent version).
    """
    engine = request.app.state.engine
    with Session(engine) as session:
        # Resolve "latest" alias for `to`.
        to_resolved = to
        if to.lower() == "latest":
            latest = session.exec(
                select(CommitVersion)
                .where(CommitVersion.commit_sha == sha)
                .order_by(CommitVersion.version_number.desc())  # type: ignore[union-attr]
            ).first()
            if latest is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"commit {sha} has no captured versions yet",
                )
            to_resolved = f"V{latest.version_number}"
        try:
            files, from_v, to_v = compare_versions(
                session, sha=sha, from_name=from_, to_name=to_resolved
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        return CompareOut(
            sha=sha,
            from_name=from_,
            to_name=to_resolved,
            from_version_number=from_v.version_number if from_v else None,
            to_version_number=to_v.version_number if to_v else None,
            files=[
                CompareFileOut(
                    file_path=f.file_path,
                    status=f.status,
                    is_binary=f.is_binary,
                    old_path=f.old_path,
                    new_path=f.new_path,
                    patch_text=f.patch_text,
                )
                for f in files
            ],
        )


@commit_versions_router.get(
    "/{sha}/versions/{n}", response_model=CommitVersionDetailOut
)
def get_commit_version(sha: str, n: int, request: Request) -> CommitVersionDetailOut:
    engine = request.app.state.engine
    with Session(engine) as session:
        version = session.exec(
            select(CommitVersion).where(
                CommitVersion.commit_sha == sha,
                CommitVersion.version_number == n,
            )
        ).first()
        if version is None:
            raise HTTPException(
                status_code=404,
                detail=f"commit {sha} has no version {n}",
            )
        files = list(
            session.exec(
                select(CommitVersionFile)
                .where(CommitVersionFile.version_id == version.id)
                .order_by(CommitVersionFile.file_path)
            ).all()
        )
        return CommitVersionDetailOut(
            version_number=version.version_number,
            created_at=version.created_at,
            trigger=version.trigger,
            triggering_thread_id=version.triggering_thread_id,
            triggering_reply_id=version.triggering_reply_id,
            files=[
                CommitVersionFileOut(
                    file_path=f.file_path,
                    status=f.status,
                    old_path=f.old_path,
                    new_path=f.new_path,
                    parent_content=snapshot_text(session, f.parent_snapshot_id),
                    commit_content=snapshot_text(session, f.commit_snapshot_id),
                )
                for f in files
            ],
        )

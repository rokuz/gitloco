from datetime import UTC, datetime

from sqlalchemy import LargeBinary
from sqlmodel import Field, Relationship, SQLModel


def _now() -> datetime:
    return datetime.now(UTC)


# DB-level values are plain strings; API/schema layer enforces literals.
# Author: "human" | "agent"
# ThreadStatus: "open" | "resolved"
# LineSide: "old" | "new"
# SnapshotKind: "commit" | "parent" | "working_tree"


class Snapshot(SQLModel, table=True):
    __tablename__ = "snapshot"

    id: int | None = Field(default=None, primary_key=True)
    content_hash: str = Field(index=True, unique=True, max_length=64)
    file_path: str
    content: bytes = Field(sa_type=LargeBinary)
    is_binary: bool = False
    originating_commit_sha: str | None = None
    originating_kind: str = "commit"
    created_at: datetime = Field(default_factory=_now)


class Thread(SQLModel, table=True):
    __tablename__ = "thread"

    id: int | None = Field(default=None, primary_key=True)
    commit_sha: str = Field(index=True)
    file_path: str = Field(index=True)
    parent_snapshot_id: int | None = Field(default=None, foreign_key="snapshot.id")
    commit_snapshot_id: int | None = Field(default=None, foreign_key="snapshot.id")
    line_side: str
    line_number: int
    status: str = Field(default="open", index=True)
    created_at: datetime = Field(default_factory=_now)
    resolved_at: datetime | None = None

    replies: list["Reply"] = Relationship(
        back_populates="thread",
        sa_relationship_kwargs={"order_by": "Reply.created_at"},
    )


class Reply(SQLModel, table=True):
    __tablename__ = "reply"

    id: int | None = Field(default=None, primary_key=True)
    thread_id: int = Field(foreign_key="thread.id", index=True)
    author: str
    body: str
    created_at: datetime = Field(default_factory=_now)

    thread: Thread | None = Relationship(back_populates="replies")


class CommitVersion(SQLModel, table=True):
    """A point-in-time capture of a commit's file set, triggered by a human
    action (thread creation or human reply). Versions are numbered sequentially
    per ``commit_sha`` starting at 1.
    """

    __tablename__ = "commit_version"

    id: int | None = Field(default=None, primary_key=True)
    commit_sha: str = Field(index=True)
    version_number: int  # 1, 2, 3, ... per commit_sha (V1, V2, ...)
    created_at: datetime = Field(default_factory=_now)
    trigger: str  # "thread_created" | "reply"
    triggering_thread_id: int | None = Field(
        default=None, foreign_key="thread.id", index=True
    )
    triggering_reply_id: int | None = Field(default=None, foreign_key="reply.id")


class CommitVersionFile(SQLModel, table=True):
    """One row per file in the commit's diff at the moment the version was
    captured. Both diff sides are pointed at via deduped ``Snapshot`` rows."""

    __tablename__ = "commit_version_file"

    id: int | None = Field(default=None, primary_key=True)
    version_id: int = Field(foreign_key="commit_version.id", index=True)
    file_path: str  # canonical path key (new_path if present, else old_path)
    status: str  # "added" | "modified" | "deleted" | "renamed" | "copied"
    old_path: str | None = None
    new_path: str | None = None
    parent_snapshot_id: int | None = Field(default=None, foreign_key="snapshot.id")
    commit_snapshot_id: int | None = Field(default=None, foreign_key="snapshot.id")

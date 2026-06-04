from datetime import UTC, datetime

from sqlalchemy import LargeBinary
from sqlmodel import Field, Relationship, SQLModel


def _now() -> datetime:
    return datetime.now(UTC)


# DB-level values are plain strings; the API/schema layer enforces literals.
# Author: "human" | "agent"
# ThreadStatus: "open" | "resolved"
# LineSide: "old" | "new"


class Snapshot(SQLModel, table=True):
    """Deduplicated blob store — file contents keyed by their sha-256 hash."""

    __tablename__ = "snapshot"

    id: int | None = Field(default=None, primary_key=True)
    content_hash: str = Field(index=True, unique=True, max_length=64)
    file_path: str
    content: bytes = Field(sa_type=LargeBinary)
    is_binary: bool = False
    created_at: datetime = Field(default_factory=_now)


class PersistentCommit(SQLModel, table=True):
    """A *logical* commit that survives rebases. The user's comment threads and
    every git hash the commit has been (its versions) hang off this. The first
    comment on a commit creates one; a rewrite just appends a new version hash.
    """

    __tablename__ = "persistent_commit"

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=_now)


class CommitVersion(SQLModel, table=True):
    """One version (content state) of a persistent commit.

    For a real commit, ``commit_hash`` is the git SHA and there is one version
    per distinct hash (rewrites append). For uncommitted changes there is no
    SHA, so ``commit_hash`` is the literal ``WORKING_TREE`` and versions are
    captured per distinct content state.
    """

    __tablename__ = "commit_version"

    id: int | None = Field(default=None, primary_key=True)
    persistent_commit_id: int = Field(foreign_key="persistent_commit.id", index=True)
    version_number: int  # 1, 2, 3, … within the persistent commit
    commit_hash: str = Field(index=True)  # git SHA, or "WORKING_TREE"
    created_at: datetime = Field(default_factory=_now)
    # Identity of the git commit (subject + author), used to auto-link a
    # rewritten commit to its persistent commit when the agent didn't record
    # the rewrite explicitly. Null for the working tree.
    subject: str | None = None
    author_name: str | None = None
    author_email: str | None = None
    author_time: int | None = None  # unix seconds

    files: list["CommitVersionFile"] = Relationship()


class CommitVersionFile(SQLModel, table=True):
    """One file in a version's diff (vs its parent), both sides pointing at
    deduped ``Snapshot`` rows."""

    __tablename__ = "commit_version_file"

    id: int | None = Field(default=None, primary_key=True)
    version_id: int = Field(foreign_key="commit_version.id", index=True)
    file_path: str  # canonical key (new_path if present, else old_path)
    status: str  # "added" | "modified" | "deleted" | "renamed" | "copied"
    old_path: str | None = None
    new_path: str | None = None
    parent_snapshot_id: int | None = Field(default=None, foreign_key="snapshot.id")
    commit_snapshot_id: int | None = Field(default=None, foreign_key="snapshot.id")


class Thread(SQLModel, table=True):
    __tablename__ = "thread"

    id: int | None = Field(default=None, primary_key=True)
    persistent_commit_id: int = Field(
        foreign_key="persistent_commit.id", index=True
    )
    # The hash/version the comment was made on (a git SHA or "WORKING_TREE").
    # The line_number is relative to this version's content.
    commit_hash: str = Field(index=True)
    file_path: str = Field(index=True)
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

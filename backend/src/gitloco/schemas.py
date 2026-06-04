from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class CommitOut(BaseModel):
    sha: str
    short_sha: str
    author_name: str
    author_email: str
    committed_at: datetime
    subject: str
    message: str = ""
    parent_shas: list[str]
    is_working_tree: bool = False


class CommitListOut(BaseModel):
    commits: list[CommitOut]
    has_working_tree_changes: bool
    branch: str | None = None


class FileDiffOut(BaseModel):
    old_path: str | None
    new_path: str | None
    status: str
    is_binary: bool
    patch_text: str


class CommitDiffOut(BaseModel):
    sha: str
    files: list[FileDiffOut]


class ReplyOut(BaseModel):
    id: int
    author: Literal["human", "agent"]
    body: str
    created_at: datetime


class ThreadOut(BaseModel):
    id: int
    commit_sha: str
    file_path: str
    line_side: Literal["old", "new"]
    line_number: int
    status: Literal["open", "resolved"]
    created_at: datetime
    resolved_at: datetime | None
    replies: list[ReplyOut]


class NewThreadIn(BaseModel):
    commit_sha: str
    file_path: str
    line_side: Literal["old", "new"]
    line_number: int
    body: str


class NewReplyIn(BaseModel):
    body: str


class CommitRewriteIn(BaseModel):
    old_sha: str
    new_sha: str


class CommitVersionListItemOut(BaseModel):
    version_number: int
    created_at: datetime
    trigger: str
    triggering_thread_id: int | None
    triggering_reply_id: int | None


class CommitVersionFileOut(BaseModel):
    file_path: str
    status: str
    old_path: str | None
    new_path: str | None
    parent_content: str | None
    commit_content: str | None


class CommitVersionDetailOut(BaseModel):
    version_number: int
    created_at: datetime
    trigger: str
    triggering_thread_id: int | None
    triggering_reply_id: int | None
    files: list[CommitVersionFileOut]


class CompareFileOut(BaseModel):
    file_path: str
    status: str
    is_binary: bool
    old_path: str | None
    new_path: str | None
    patch_text: str


class CompareOut(BaseModel):
    sha: str
    from_name: str
    to_name: str
    from_version_number: int | None
    to_version_number: int | None
    files: list[CompareFileOut]


class FileHistoryCommitOut(BaseModel):
    sha: str
    short_sha: str
    author_name: str
    author_email: str
    committed_at: datetime
    subject: str
    parent_shas: list[str]
    status: str
    old_path: str | None
    new_path: str | None
    patch_text: str


class FileHistoryOut(BaseModel):
    file_path: str
    since: str | None
    commits: list[FileHistoryCommitOut]
    working_tree_patch: str | None


class FileAtOut(BaseModel):
    file_path: str
    sha: str
    exists: bool
    is_binary: bool
    content: str | None

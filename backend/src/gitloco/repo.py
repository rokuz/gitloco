from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pygit2


class NotAGitRepoError(Exception):
    pass


@dataclass(frozen=True)
class CommitInfo:
    sha: str
    short_sha: str
    author_name: str
    author_email: str
    committed_at: datetime
    subject: str
    parent_shas: list[str]


WORKING_TREE_SHA = "WORKING_TREE"


def open_repo(path: Path) -> pygit2.Repository:
    discovered = pygit2.discover_repository(str(path))
    if discovered is None:
        raise NotAGitRepoError(f"{path} is not inside a git repository")
    return pygit2.Repository(discovered)


def list_commits(repo: pygit2.Repository) -> list[CommitInfo]:
    if repo.is_empty or repo.head_is_unborn:
        return []
    head = repo.head.target
    walker = repo.walk(head, pygit2.GIT_SORT_TOPOLOGICAL | pygit2.GIT_SORT_TIME)
    commits: list[CommitInfo] = []
    for commit in walker:
        commits.append(_to_commit_info(commit))
    return commits


def has_working_tree_changes(repo: pygit2.Repository) -> bool:
    status = repo.status(untracked_files="normal", ignored=False)
    return any(flags != pygit2.GIT_STATUS_CURRENT for flags in status.values())


def _to_commit_info(commit: pygit2.Commit) -> CommitInfo:
    sha = str(commit.id)
    subject = commit.message.splitlines()[0] if commit.message else ""
    committed_at = datetime.fromtimestamp(commit.commit_time, tz=timezone.utc)
    return CommitInfo(
        sha=sha,
        short_sha=sha[:7],
        author_name=commit.author.name,
        author_email=commit.author.email,
        committed_at=committed_at,
        subject=subject,
        parent_shas=[str(p) for p in commit.parent_ids],
    )

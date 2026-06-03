from dataclasses import dataclass

import pygit2

from gitloco.repo import WORKING_TREE_SHA

_STATUS_MAP = {
    pygit2.GIT_DELTA_ADDED: "added",
    pygit2.GIT_DELTA_DELETED: "deleted",
    pygit2.GIT_DELTA_MODIFIED: "modified",
    pygit2.GIT_DELTA_RENAMED: "renamed",
    pygit2.GIT_DELTA_COPIED: "copied",
    pygit2.GIT_DELTA_UNTRACKED: "added",
    pygit2.GIT_DELTA_TYPECHANGE: "modified",
}


@dataclass(frozen=True)
class FileDiff:
    old_path: str | None
    new_path: str | None
    status: str
    is_binary: bool
    patch_text: str


def _diff_for_commit(repo: pygit2.Repository, sha: str) -> pygit2.Diff:
    obj = repo.get(sha)
    if obj is None:
        raise KeyError(sha)
    if isinstance(obj, pygit2.Tag):
        obj = obj.peel(pygit2.Commit)
    if not isinstance(obj, pygit2.Commit):
        raise ValueError(f"{sha} is not a commit")
    if obj.parents:
        return obj.parents[0].tree.diff_to_tree(obj.tree, context_lines=3)
    return obj.tree.diff_to_tree(swap=True, context_lines=3)


def _diff_for_working_tree(repo: pygit2.Repository) -> pygit2.Diff:
    if repo.is_empty or repo.head_is_unborn:
        # Synthesize a diff from an empty tree to the workdir.
        empty_tree_oid = repo.TreeBuilder().write()
        empty_tree = repo[empty_tree_oid]
        return empty_tree.diff_to_workdir(
            context_lines=3,
            flags=(
                pygit2.GIT_DIFF_INCLUDE_UNTRACKED
                | pygit2.GIT_DIFF_RECURSE_UNTRACKED_DIRS
                | pygit2.GIT_DIFF_SHOW_UNTRACKED_CONTENT
            ),
        )
    head_tree = repo[repo.head.target].tree
    return head_tree.diff_to_workdir(
        context_lines=3,
        flags=(
            pygit2.GIT_DIFF_INCLUDE_UNTRACKED
            | pygit2.GIT_DIFF_RECURSE_UNTRACKED_DIRS
            | pygit2.GIT_DIFF_SHOW_UNTRACKED_CONTENT
        ),
    )


def get_diff(repo: pygit2.Repository, sha: str) -> list[FileDiff]:
    diff = (
        _diff_for_working_tree(repo) if sha == WORKING_TREE_SHA else _diff_for_commit(repo, sha)
    )
    diff.find_similar()
    out: list[FileDiff] = []
    for patch in diff:
        delta = patch.delta
        status = _STATUS_MAP.get(delta.status, "modified")
        out.append(
            FileDiff(
                old_path=delta.old_file.path or None,
                new_path=delta.new_file.path or None,
                status=status,
                is_binary=bool(delta.is_binary),
                patch_text=patch.text or "",
            )
        )
    return out

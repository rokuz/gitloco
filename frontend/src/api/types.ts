export interface Commit {
  sha: string;
  short_sha: string;
  author_name: string;
  author_email: string;
  committed_at: string;
  subject: string;
  message: string;
  parent_shas: string[];
  is_working_tree: boolean;
}

export interface CommitList {
  commits: Commit[];
  has_working_tree_changes: boolean;
  branch: string | null;
}

export const WORKING_TREE_SHA = "WORKING_TREE";

export type FileStatus = "added" | "deleted" | "modified" | "renamed" | "copied";

export interface FileDiff {
  old_path: string | null;
  new_path: string | null;
  status: FileStatus;
  is_binary: boolean;
  patch_text: string;
}

export interface CommitDiff {
  sha: string;
  files: FileDiff[];
}

export type LineSide = "old" | "new";
export type Author = "human" | "agent";
export type ThreadStatus = "open" | "resolved";

export interface Reply {
  id: number;
  author: Author;
  body: string;
  created_at: string;
}

export interface Thread {
  id: number;
  commit_sha: string;
  file_path: string;
  line_side: LineSide;
  line_number: number;
  status: ThreadStatus;
  created_at: string;
  resolved_at: string | null;
  replies: Reply[];
}

export interface NewThreadIn {
  commit_sha: string;
  file_path: string;
  line_side: LineSide;
  line_number: number;
  body: string;
}

export interface CommitVersion {
  version_number: number;
  commit_hash: string;
  short_hash: string;
  subject: string | null;
  created_at: string;
}

export type CompareStatus =
  | "added"
  | "deleted"
  | "modified"
  | "renamed"
  | "copied"
  | "unchanged"
  | "binary";

export interface CompareFile {
  file_path: string;
  status: CompareStatus;
  is_binary: boolean;
  old_path: string | null;
  new_path: string | null;
  patch_text: string;
}

export interface CompareOut {
  sha: string;
  from_name: string;
  to_name: string;
  from_version_number: number | null;
  to_version_number: number | null;
  files: CompareFile[];
}

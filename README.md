# GitLoco

Local code-review tool for AI-generated git changes. A human leaves comments on diff lines through a browser UI; an AI agent (Claude) reads them, replies, and amends the original commits via rebase. Threads survive the rebase because GitLoco snapshots both sides of the diff at comment time.

![Overview](docs/img/01-overview.png)

## What it does

- Runs as a one-process-per-repo local server (like `jupyter`, `storybook`).
- Shows the repo's commit history + working-tree changes in a unified diff view with syntax highlighting.
- Lets you anchor comment threads to specific lines of specific commits.
- Exposes those threads to AI agents via REST **and** an MCP server in the same process.
- Captures **all** files touched by a commit on every human action so the agent has full multi-file context.
- LAN-accessible — open the same URL from your phone on the couch.
- Single-user local. No auth, no multi-tenancy.

## Quick start

```bash
# One-time install
( cd backend  && uv sync )
( cd frontend && npm install )

# Run backend + frontend together (defaults to the current directory)
./run.sh                 # opens http://localhost:5173

# Or point it at another repo
./run.sh /path/to/repo
```

To wire Claude Code into the running server (so the `/gitloco` slash command and the `gitloco` MCP tools appear), run once in the repo you want to review:

```bash
cd /path/to/your/repo
gitloco --install-mcp    # writes .mcp.json + .claude/commands/gitloco.md
```

On first launch macOS may prompt to allow the Python process to accept incoming connections. Click **Allow** and the LAN URL (printed on startup) becomes reachable from your phone on the same Wi‑Fi.

## Screenshots

### Diff view with syntax highlighting

![Diff view](docs/img/02-diff-syntax-highlight.png)

### Inline comment threads — human ↔ AI back-and-forth right on the line

![Inline thread](docs/img/03-inline-thread.png)

### Version compare — switch and compare snapshots of a commit over time

Every human action (new thread or human reply) captures the full file set as a new version. The picker defaults to **Base → Latest**.

![Version compare](docs/img/04-version-compare.png)

### Mobile

The sidebar becomes a slide-over drawer below the `md` breakpoint, so the same UI works from a phone over LAN.

![Mobile drawer](docs/img/05-mobile-drawer.png)

## Stack

- **Backend:** Python 3.12, FastAPI, pygit2, SQLModel + SQLite, official `mcp` SDK (streamable‑HTTP transport mounted in‑process at `/mcp/`).
- **Frontend:** Vite + React 19 + TypeScript, Tailwind v4, TanStack Query, `react-diff-view`, refractor (Prism) for syntax highlighting.
- **Storage:** `.gitloco/comments.db` inside the reviewed repo (auto‑gitignored).

## CLI

```
gitloco [PATH] [OPTIONS]

  --host TEXT             Bind address (default 0.0.0.0; use 127.0.0.1 to
                          disable LAN access)
  --port INT              Port (default 7777)
  --no-browser            Do not open a browser on launch
  --install-command       Write .claude/commands/gitloco.md and exit
  --install-mcp           Write/update .mcp.json so Claude Code discovers
                          the local GitLoco MCP server (implies
                          --install-command)
  --force                 Overwrite an existing slash-command file
```

## MCP tools exposed to the agent

- `list_open_threads(commit_sha?)` — threads to address, ordered oldest commit first
- `get_thread(thread_id)` — full context: replies, primary file snapshots, `all_files` for the whole commit, `history_since`, `working_tree_patch`, `current_content`, `latest_version_number`
- `reply_to_thread(thread_id, body)`
- `list_commit_versions(commit_sha)` / `get_commit_version(commit_sha, n)`
- `get_file_history(file_path, since_commit_sha?)` / `get_file_at(commit_sha, file_path)`
- `get_commit_diff(commit_sha)` / `list_commits_tool()`

There is intentionally no `resolve_thread` tool. Humans resolve via the UI.

## Status

v1 — usable end-to-end.

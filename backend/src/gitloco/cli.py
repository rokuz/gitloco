import json
import socket
import sys
import threading
import time
import webbrowser
from importlib.resources import files
from pathlib import Path

import click

from gitloco import __version__
from gitloco.config import Settings
from gitloco.repo import NotAGitRepoError, open_repo

# NOTE: `uvicorn` and `gitloco.app` (which pulls in fastapi, the mcp SDK,
# sqlmodel, …) are imported lazily inside main(). Together they take ~0.5s+ to
# import; doing it at module load would make `gitloco` sit silent before any
# output, and a Ctrl-C during that window escapes Click's handler and dumps a
# raw traceback. Deferring the import gives instant feedback and a clean abort.

GITIGNORE_ENTRY = ".gitloco/\n"
CLAUDE_COMMAND_RELPATH = Path(".claude/commands/gitloco.md")
MCP_CONFIG_RELPATH = Path(".mcp.json")
CLAUDE_MD_RELPATH = Path("CLAUDE.md")
CLAUDE_MD_START = "<!-- gitloco-start"
CLAUDE_MD_END = "<!-- gitloco-end -->"


def _find_free_port(preferred: int, host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, preferred))
            return preferred
        except OSError:
            pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def _detect_lan_ip() -> str | None:
    """Best-effort LAN IP detection.

    Opens a UDP socket to a non-routable address — no packets sent — and reads
    the OS-assigned local address. Returns None if we can't determine one.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
        except OSError:
            return None
    if ip.startswith("127.") or ip == "0.0.0.0":
        return None
    return ip


def _ensure_data_dir(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)


def _file_log_config(log_file: Path) -> dict:
    """uvicorn logging config that writes the server + access logs to a file
    instead of the console, so the terminal stays clean (just our own echoes)."""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "()": "uvicorn.logging.DefaultFormatter",
                "fmt": "%(asctime)s %(levelprefix)s %(message)s",
                "use_colors": False,
            },
            "access": {
                "()": "uvicorn.logging.AccessFormatter",
                "fmt": '%(asctime)s %(levelprefix)s %(client_addr)s - '
                '"%(request_line)s" %(status_code)s',
                "use_colors": False,
            },
        },
        "handlers": {
            "default": {
                "class": "logging.FileHandler",
                "filename": str(log_file),
                "formatter": "default",
            },
            "access": {
                "class": "logging.FileHandler",
                "filename": str(log_file),
                "formatter": "access",
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"level": "INFO"},
            "uvicorn.access": {
                "handlers": ["access"],
                "level": "INFO",
                "propagate": False,
            },
        },
    }


def _ensure_gitignore(repo_root: Path) -> None:
    gitignore = repo_root / ".gitignore"
    if gitignore.exists():
        text = gitignore.read_text(encoding="utf-8")
        lines = {line.strip().rstrip("/") for line in text.splitlines() if line.strip()}
        if ".gitloco" in lines:
            return
        suffix = "" if text.endswith("\n") else "\n"
        gitignore.write_text(text + suffix + GITIGNORE_ENTRY, encoding="utf-8")
    else:
        gitignore.write_text(GITIGNORE_ENTRY, encoding="utf-8")


def _set_process_title() -> None:
    """Show up as ``gitloco`` in ps/Activity Monitor instead of ``python``.

    Best-effort: setproctitle needs a native build, so never let a failure
    here block startup."""
    try:
        import setproctitle

        setproctitle.setproctitle("gitloco")
    except Exception:
        pass


def _open_browser_when_ready(url: str, delay: float = 0.6) -> None:
    def _open() -> None:
        time.sleep(delay)
        webbrowser.open(url)

    threading.Thread(target=_open, daemon=True).start()


def _install_claude_command(repo_root: Path, *, force: bool) -> Path:
    template = files("gitloco.templates").joinpath("gitloco_command.md").read_text()
    target = repo_root / CLAUDE_COMMAND_RELPATH
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not force:
        raise FileExistsError(target)
    target.write_text(template, encoding="utf-8")
    return target


def _install_claude_md_section(repo_root: Path) -> tuple[Path, str]:
    """Append (or replace) the GitLoco stanza in the repo's CLAUDE.md.

    Returns ``(path, action)`` where action is one of ``"created"``,
    ``"appended"``, or ``"updated"`` so the caller can log accurately.
    """
    section = (
        files("gitloco.templates").joinpath("claude_md_section.md").read_text()
    )
    target = repo_root / CLAUDE_MD_RELPATH
    if not target.exists():
        target.write_text(section if section.endswith("\n") else section + "\n", encoding="utf-8")
        return target, "created"

    existing = target.read_text(encoding="utf-8")
    start_idx = existing.find(CLAUDE_MD_START)
    end_idx = existing.find(CLAUDE_MD_END)
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        # Replace the existing GitLoco block in place.
        end_after = end_idx + len(CLAUDE_MD_END)
        # Strip a trailing newline immediately after the end marker so we don't
        # accumulate blank lines on each rewrite.
        if end_after < len(existing) and existing[end_after] == "\n":
            end_after += 1
        new_body = section if section.endswith("\n") else section + "\n"
        merged = existing[:start_idx] + new_body + existing[end_after:]
        target.write_text(merged, encoding="utf-8")
        return target, "updated"

    # Append below the existing content with a blank-line separator.
    separator = "" if existing.endswith("\n\n") else ("\n" if existing.endswith("\n") else "\n\n")
    target.write_text(existing + separator + section, encoding="utf-8")
    return target, "appended"


def _mcp_url(port: int) -> str:
    return f"http://127.0.0.1:{port}/mcp/"


def _install_mcp_config(repo_root: Path, *, port: int) -> Path:
    target = repo_root / MCP_CONFIG_RELPATH
    config: dict = {}
    if target.exists():
        try:
            config = json.loads(target.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            config = {}
    servers = config.setdefault("mcpServers", {})
    servers["gitloco"] = {"type": "http", "url": _mcp_url(port)}
    target.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return target


def _sync_mcp_port(repo_root: Path, *, port: int) -> bool:
    """Keep .mcp.json's gitloco URL pointing at the port we actually bound to.

    `gitloco` falls back to a random free port when the requested one is taken,
    which leaves a stale URL in .mcp.json and breaks Claude Code's connection.
    Update it in place on every startup. Only touches an existing gitloco entry
    (we don't create the file — that's opt-in via --install-mcp). Returns True
    if the URL was changed.
    """
    target = repo_root / MCP_CONFIG_RELPATH
    if not target.exists():
        return False
    try:
        config = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    entry = config.get("mcpServers", {}).get("gitloco")
    if not isinstance(entry, dict):
        return False
    want = _mcp_url(port)
    if entry.get("url") == want:
        return False
    entry["url"] = want
    try:
        target.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    except OSError:
        return False
    return True


@click.command()
@click.argument(
    "path",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=Path.cwd,
)
@click.option(
    "--host",
    default="0.0.0.0",
    show_default=True,
    help="Bind address. Use 127.0.0.1 to disable LAN access.",
)
@click.option("--port", type=int, default=7777, show_default=True)
@click.option("--no-browser", is_flag=True, help="Do not open a browser.")
@click.option(
    "--install-command",
    "install_command",
    is_flag=True,
    help="Write the /gitloco Claude Code slash-command template into "
    ".claude/commands/gitloco.md and exit.",
)
@click.option(
    "--install-mcp",
    "install_mcp",
    is_flag=True,
    help="Write/update .mcp.json so Claude Code auto-discovers the local "
    "GitLoco MCP server. Implies the slash-command install too.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite an existing slash-command file (used with --install-command).",
)
@click.version_option(__version__, prog_name="gitloco")
def main(
    path: Path,
    host: str,
    port: int,
    no_browser: bool,
    install_command: bool,
    install_mcp: bool,
    force: bool,
) -> None:
    """Launch GitLoco for a local git repository."""
    _set_process_title()
    try:
        repo = open_repo(path)
    except NotAGitRepoError as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(2)

    repo_root = Path(repo.workdir).resolve() if repo.workdir else path.resolve()

    if install_command or install_mcp:
        try:
            cmd_target = _install_claude_command(repo_root, force=force)
        except FileExistsError as exc:
            click.echo(
                f"error: {exc.args[0]} already exists. Pass --force to overwrite.",
                err=True,
            )
            sys.exit(1)
        click.echo(f"Wrote {cmd_target}")
        if install_mcp:
            mcp_target = _install_mcp_config(repo_root, port=port)
            click.echo(f"Wrote {mcp_target} (gitloco entry → http://127.0.0.1:{port}/mcp/)")
            claude_md_target, action = _install_claude_md_section(repo_root)
            click.echo(f"{action.capitalize()} {claude_md_target} (GitLoco review section)")
        return
    # Immediate feedback before the (slowish) heavy imports below, so the user
    # never stares at a silent terminal and assumes it hung.
    click.echo(f"Starting GitLoco {__version__}…")

    # Lazy heavy imports — see note at top of module.
    import uvicorn

    from gitloco.app import create_app

    settings = Settings.for_repo(repo_root)
    _ensure_data_dir(settings.data_dir)
    _ensure_gitignore(repo_root)

    chosen_port = _find_free_port(port, host)
    loopback_url = f"http://127.0.0.1:{chosen_port}"
    lan_ip = _detect_lan_ip() if host in ("0.0.0.0", "::") else None
    lan_url = f"http://{lan_ip}:{chosen_port}" if lan_ip else None

    # Keep .mcp.json pointing at the port we actually bound to, so Claude Code's
    # MCP connection doesn't break when we fall back off the requested port.
    if _sync_mcp_port(repo_root, port=chosen_port):
        click.echo(f"Updated {MCP_CONFIG_RELPATH} → {_mcp_url(chosen_port)}")

    app = create_app(settings)
    log_file = settings.data_dir / "server.log"
    click.echo(f"GitLoco {__version__}  ·  {repo_root}")
    click.echo(f"  Local:   {loopback_url}")
    if lan_url:
        click.echo(f"  Network: {lan_url}")
    elif host == "0.0.0.0":
        click.echo("  Network: (could not detect LAN IP)")
    click.echo(f"  MCP:     {_mcp_url(chosen_port)}")
    click.echo(f"  Logs:    {log_file}")
    click.echo("  Ctrl-C to stop")

    if not no_browser:
        _open_browser_when_ready(loopback_url)

    uvicorn.run(
        app,
        host=host,
        port=chosen_port,
        log_config=_file_log_config(log_file),
    )


if __name__ == "__main__":
    main()

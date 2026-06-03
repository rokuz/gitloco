from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gitloco import __version__
from gitloco.config import Settings
from gitloco.db import make_engine
from gitloco.mcp_server import build_mcp
from gitloco.repo import open_repo
from gitloco.routers import commits as commits_router
from gitloco.routers import files as files_router
from gitloco.routers import threads as threads_router


def create_app(settings: Settings) -> FastAPI:
    repo = open_repo(settings.repo_path)
    engine = make_engine(settings.db_path)
    mcp = build_mcp(engine=engine, repo=repo, repo_path=str(settings.repo_path))
    # Force lazy session_manager init by building the Starlette app once.
    mcp_app = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        async with mcp.session_manager.run():
            yield

    app = FastAPI(title="GitLoco", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.repo = repo
    app.state.engine = engine

    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|100\.\d+\.\d+\.\d+)(:\d+)?$",
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(commits_router.router)
    app.include_router(threads_router.router)
    app.include_router(threads_router.commit_versions_router)
    app.include_router(files_router.router)
    app.mount("/mcp", mcp_app)

    @app.get("/api/health")
    def health() -> dict[str, str | Path]:
        return {
            "status": "ok",
            "version": __version__,
            "repo": str(settings.repo_path),
        }

    return app

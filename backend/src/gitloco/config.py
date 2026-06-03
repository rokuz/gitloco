from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GITLOCO_", env_file=None)

    repo_path: Path
    data_dir: Path
    db_path: Path
    host: str = "127.0.0.1"
    port: int = 7777

    @classmethod
    def for_repo(cls, repo_path: Path) -> "Settings":
        repo_path = repo_path.resolve()
        data_dir = repo_path / ".gitloco"
        return cls(
            repo_path=repo_path,
            data_dir=data_dir,
            db_path=data_dir / "comments.db",
        )

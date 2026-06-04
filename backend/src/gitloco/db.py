from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, inspect, text
from sqlmodel import Session, SQLModel, create_engine

from gitloco import models  # noqa: F401  — ensure tables are registered

# Columns added to existing tables after v1. SQLModel.create_all() creates new
# tables but never alters existing ones, so we add these by hand on startup for
# databases created by an older GitLoco. (Lightweight stand-in for Alembic.)
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "thread": {
        "commit_subject": "TEXT",
        "commit_author_name": "TEXT",
        "commit_author_email": "TEXT",
        "commit_author_time": "INTEGER",
    },
}


def _add_missing_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            if table not in existing_tables:
                continue
            present = {c["name"] for c in inspector.get_columns(table)}
            for name, sql_type in columns.items():
                if name not in present:
                    conn.execute(
                        text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {sql_type}')
                    )


def make_engine(db_path: Path) -> Engine:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    _add_missing_columns(engine)  # before create_all, on the pre-existing schema
    SQLModel.metadata.create_all(engine)  # adds any brand-new tables
    return engine


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

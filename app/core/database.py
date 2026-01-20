import os
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/app.db")
ALTER_TABLE = "ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)"


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_dir(database_url: str) -> None:
    if not database_url.startswith("sqlite:///"):
        return
    path = database_url.replace("sqlite:///", "", 1)
    if path.startswith("./"):
        path = path[2:]
    dir_path = Path(path).parent
    if str(dir_path) and str(dir_path) != ".":
        dir_path.mkdir(parents=True, exist_ok=True)


_connect_args = {
    "check_same_thread": False
} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def init_db() -> None:
    _ensure_sqlite_dir(DATABASE_URL)
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_password_column()


def _ensure_password_column() -> None:
    with engine.begin() as connection:
        if DATABASE_URL.startswith("sqlite"):
            rows = connection.execute(
                text("PRAGMA table_info(users)")
            ).fetchall()
            columns = {row[1] for row in rows}
            if "password_hash" not in columns:
                connection.execute(
                    text(ALTER_TABLE)
                )
        else:
            rows = connection.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='users' AND column_name='password_hash'"
                )
            ).fetchall()
            if not rows:
                connection.execute(
                    text(ALTER_TABLE)
                )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

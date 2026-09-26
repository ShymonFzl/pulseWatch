import os
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import NoReturn

import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import URL, create_engine, make_url, text
from sqlalchemy.exc import OperationalError

from pulsewatch.config import Settings

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def _database_unavailable(reason: str) -> NoReturn:
    # In CI a missing database is a failure, never a silent skip.
    if os.environ.get("CI"):
        pytest.fail(reason)
    pytest.skip(f"{reason}: start it with `docker compose up -d db` (see .env.example)")


def _alembic_config(url: URL) -> Config:
    config = Config(ALEMBIC_INI)
    config.attributes["database_url"] = url.render_as_string(hide_password=False)
    config.attributes["configure_logger"] = False
    return config


@contextmanager
def _throwaway_database() -> Iterator[URL]:
    """Create an empty database on the DATABASE_URL server, and drop it afterwards."""
    try:
        server_url = make_url(str(Settings().database_url))  # type: ignore[call-arg]
    except ValidationError:
        _database_unavailable("DATABASE_URL is not set")

    server = create_engine(server_url, isolation_level="AUTOCOMMIT")
    name = f"pulsewatch_test_{uuid.uuid4().hex[:12]}"
    try:
        with server.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    except OperationalError as exc:
        server.dispose()
        _database_unavailable(f"PostgreSQL is not reachable ({exc.orig})")

    try:
        yield server_url.set(database=name)
    finally:
        with server.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        server.dispose()


@pytest.fixture(scope="session")
def database_url() -> Iterator[URL]:
    """Empty throwaway database, for tests that manage the schema themselves."""
    with _throwaway_database() as url:
        yield url


@pytest.fixture(scope="session")
def migrated_database_url() -> Iterator[URL]:
    """Throwaway database migrated to the latest schema."""
    with _throwaway_database() as url:
        command.upgrade(_alembic_config(url), "head")
        yield url


@pytest.fixture(scope="session")
def alembic_config() -> Callable[[URL], Config]:
    return _alembic_config

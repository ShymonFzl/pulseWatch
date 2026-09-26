import os
import uuid
from collections.abc import Iterator
from typing import NoReturn

import pytest
from pydantic import ValidationError
from sqlalchemy import URL, create_engine, make_url, text
from sqlalchemy.exc import OperationalError

from pulsewatch.config import Settings


def _database_unavailable(reason: str) -> NoReturn:
    # In CI a missing database is a failure, never a silent skip.
    if os.environ.get("CI"):
        pytest.fail(reason)
    pytest.skip(f"{reason}: start it with `docker compose up -d db` (see .env.example)")


@pytest.fixture(scope="session")
def database_url() -> Iterator[URL]:
    """URL of a throwaway database, created for the test session and dropped afterwards."""
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

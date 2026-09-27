from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import URL, create_engine, text

from pulsewatch.api.main import create_app
from pulsewatch.config import Settings


@pytest.fixture
def client(migrated_database_url: URL) -> Iterator[TestClient]:
    # Every test starts from empty tables.
    engine = create_engine(migrated_database_url)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE sites, checks RESTART IDENTITY"))
    engine.dispose()

    url = migrated_database_url.render_as_string(hide_password=False)
    settings = Settings.model_validate({"database_url": url})
    with TestClient(create_app(settings)) as client:
        yield client

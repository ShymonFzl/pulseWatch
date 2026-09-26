from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import URL

from pulsewatch.api.main import create_app
from pulsewatch.config import Settings

# Nothing listens on port 1: connections are refused immediately.
UNREACHABLE_DATABASE_URL = "postgresql+psycopg://user:password@127.0.0.1:1/none"


def client_for(database_url: str) -> TestClient:
    settings = Settings.model_validate({"database_url": database_url})
    return TestClient(create_app(settings))


@pytest.fixture
def client_without_database() -> Iterator[TestClient]:
    with client_for(UNREACHABLE_DATABASE_URL) as client:
        yield client


def test_liveness_is_ok_without_database(client_without_database: TestClient) -> None:
    response = client_without_database.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_is_unavailable_without_database(client_without_database: TestClient) -> None:
    response = client_without_database.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


@pytest.mark.db
def test_readiness_is_ok_with_database(database_url: URL) -> None:
    with client_for(database_url.render_as_string(hide_password=False)) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

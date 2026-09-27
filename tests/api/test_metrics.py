from collections.abc import Iterator

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from pulsewatch.api.main import create_app
from pulsewatch.config import Settings
from tests.api.test_health import UNREACHABLE_DATABASE_URL


@pytest.fixture
def app_without_database() -> Iterator[TestClient]:
    settings = Settings.model_validate({"database_url": UNREACHABLE_DATABASE_URL})
    app = create_app(settings)

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("unexpected failure")

    @app.get("/teapot")
    def teapot() -> None:
        raise HTTPException(418)

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_metrics_expose_request_count_and_latency(app_without_database: TestClient) -> None:
    app_without_database.get("/health")
    app_without_database.get("/health")

    response = app_without_database.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain; version=")
    body = response.text
    assert 'pulsewatch_http_requests_total{method="GET",route="/health",status="200"} 2.0' in body
    assert (
        'pulsewatch_http_request_duration_seconds_count{method="GET",route="/health"} 2.0' in body
    )
    # Standard process metrics are included.
    assert "process_cpu_seconds_total" in body


def test_unknown_paths_share_one_route_label(app_without_database: TestClient) -> None:
    app_without_database.get("/does-not-exist")
    app_without_database.get("/nor-this/42")

    body = app_without_database.get("/metrics").text

    assert 'route="unmatched",status="404"} 2.0' in body
    assert "does-not-exist" not in body


def test_error_statuses_are_recorded(app_without_database: TestClient) -> None:
    assert app_without_database.get("/teapot").status_code == 418
    assert app_without_database.get("/boom").status_code == 500

    body = app_without_database.get("/metrics").text

    assert 'route="/teapot",status="418"} 1.0' in body
    assert 'route="/boom",status="500"} 1.0' in body


def test_metrics_endpoint_is_not_in_openapi(app_without_database: TestClient) -> None:
    assert "/metrics" not in app_without_database.get("/openapi.json").json()["paths"]


@pytest.mark.db
def test_routes_are_labelled_by_template(client: TestClient) -> None:
    site_id = client.post("/sites", json={"name": "x", "url": "https://x.example.com/"}).json()[
        "id"
    ]
    client.get(f"/sites/{site_id}")

    body = client.get("/metrics").text

    assert 'route="/sites/{site_id}",status="200"} 1.0' in body
    assert f'route="/sites/{site_id}"' not in body

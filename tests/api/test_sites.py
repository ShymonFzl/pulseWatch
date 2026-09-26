from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import URL, create_engine, text

from pulsewatch.api.main import create_app
from pulsewatch.config import Settings

pytestmark = pytest.mark.db

BIGINT_MAX = 2**63 - 1


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


def create_site(
    client: TestClient, name: str = "Example", url: str = "https://example.com/"
) -> int:
    response = client.post("/sites", json={"name": name, "url": url})
    assert response.status_code == 201, response.text
    site_id: int = response.json()["id"]
    return site_id


# --- nominal cases -----------------------------------------------------------


def test_create_site(client: TestClient) -> None:
    response = client.post("/sites", json={"name": "  Example  ", "url": "https://Example.com"})

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Example"
    # Normalized: lowercase host and "/" path.
    assert body["url"] == "https://example.com/"
    assert body["id"] > 0
    assert body["created_at"]
    assert "interval_seconds" not in body
    assert response.headers["location"].endswith(f"/sites/{body['id']}")


def test_list_sites_in_creation_order(client: TestClient) -> None:
    first = create_site(client, "First", "https://first.example.com/")
    second = create_site(client, "Second", "http://second.example.com/status")

    response = client.get("/sites")

    assert response.status_code == 200
    assert [site["id"] for site in response.json()] == [first, second]


def test_list_sites_paginates(client: TestClient) -> None:
    ids = [create_site(client, f"Site {i}", f"https://site{i}.example.com/") for i in range(3)]

    response = client.get("/sites", params={"limit": 1, "offset": 1})

    assert [site["id"] for site in response.json()] == [ids[1]]


def test_list_sites_empty(client: TestClient) -> None:
    response = client.get("/sites")

    assert response.status_code == 200
    assert response.json() == []


def test_get_site(client: TestClient) -> None:
    site_id = create_site(client)

    response = client.get(f"/sites/{site_id}")

    assert response.status_code == 200
    assert response.json()["url"] == "https://example.com/"


def test_delete_site(client: TestClient) -> None:
    site_id = create_site(client)

    response = client.delete(f"/sites/{site_id}")

    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"/sites/{site_id}").status_code == 404


# --- 404 --------------------------------------------------------------------


@pytest.mark.parametrize("method", ["GET", "DELETE"])
def test_unknown_site_returns_404(client: TestClient, method: str) -> None:
    response = client.request(method, "/sites/999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Site not found"}


# --- 409 --------------------------------------------------------------------


@pytest.mark.parametrize(
    "duplicate_url",
    ["https://example.com/", "https://EXAMPLE.com", "https://example.com"],
)
def test_duplicate_url_returns_409(client: TestClient, duplicate_url: str) -> None:
    create_site(client, url="https://example.com/")

    response = client.post("/sites", json={"name": "Again", "url": duplicate_url})

    assert response.status_code == 409
    assert response.json() == {"detail": "A site with this URL already exists"}


def test_url_can_be_reused_after_deletion(client: TestClient) -> None:
    site_id = create_site(client)
    client.delete(f"/sites/{site_id}")

    response = client.post("/sites", json={"name": "Example", "url": "https://example.com/"})

    assert response.status_code == 201


# --- 422 --------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"name": "x", "url": "ftp://example.com/"}, id="non-http-scheme"),
        pytest.param({"name": "x", "url": "file:///etc/passwd"}, id="file-scheme"),
        pytest.param({"name": "x", "url": "not a url"}, id="not-a-url"),
        pytest.param({"name": "x", "url": "https://user:pass@example.com/"}, id="credentials"),
        pytest.param({"name": "x", "url": "https://example.com/" + "a" * 2048}, id="url-too-long"),
        pytest.param({"name": "   ", "url": "https://example.com/"}, id="blank-name"),
        pytest.param({"name": "x" * 201, "url": "https://example.com/"}, id="name-too-long"),
        pytest.param({"url": "https://example.com/"}, id="missing-name"),
        pytest.param(
            {"name": "x", "url": "https://example.com/", "interval_seconds": 5},
            id="unknown-field",
        ),
    ],
)
def test_invalid_site_returns_422(client: TestClient, payload: dict[str, object]) -> None:
    response = client.post("/sites", json=payload)

    assert response.status_code == 422
    assert client.get("/sites").json() == []


@pytest.mark.parametrize("site_id", ["0", "-1", "abc", str(BIGINT_MAX + 1)])
def test_invalid_site_id_returns_422(client: TestClient, site_id: str) -> None:
    assert client.get(f"/sites/{site_id}").status_code == 422
    assert client.delete(f"/sites/{site_id}").status_code == 422


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 501}, {"offset": -1}])
def test_invalid_pagination_returns_422(client: TestClient, params: dict[str, int]) -> None:
    assert client.get("/sites", params=params).status_code == 422


# --- OpenAPI ----------------------------------------------------------------


def test_openapi_documents_sites_endpoints(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]

    assert set(paths["/sites"]) == {"get", "post"}
    assert set(paths["/sites/{site_id}"]) == {"get", "delete"}
    assert {"201", "409", "422"} <= set(paths["/sites"]["post"]["responses"])
    assert {"204", "404", "422"} <= set(paths["/sites/{site_id}"]["delete"]["responses"])
    assert {"200", "404", "422"} <= set(paths["/sites/{site_id}"]["get"]["responses"])
    assert "interval_seconds" not in schema["components"]["schemas"]["SiteRead"]["properties"]

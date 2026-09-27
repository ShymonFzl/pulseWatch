from collections.abc import Iterator

import pytest

from tests.worker.fake_site import FakeSite, serve_fake_site


@pytest.fixture
def fake_site() -> Iterator[FakeSite]:
    with serve_fake_site() as site:
        yield site

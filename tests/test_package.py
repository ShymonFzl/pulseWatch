import pulsewatch


def test_version_matches_package_metadata() -> None:
    assert pulsewatch.__version__ == "0.1.0"

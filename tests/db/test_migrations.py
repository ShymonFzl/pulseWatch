from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import URL, create_engine, inspect, text

pytestmark = pytest.mark.db

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def alembic_config(url: URL) -> Config:
    config = Config(ALEMBIC_INI)
    config.attributes["database_url"] = url.render_as_string(hide_password=False)
    config.attributes["configure_logger"] = False
    return config


def table_names(url: URL) -> set[str]:
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_migrations_upgrade_downgrade_round_trip(database_url: URL) -> None:
    config = alembic_config(database_url)

    command.upgrade(config, "head")
    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)
        assert {"sites", "checks"} <= set(inspector.get_table_names())

        [index] = [
            ix
            for ix in inspector.get_indexes("checks")
            if ix["name"] == "ix_checks_site_id_checked_at"
        ]
        assert index["column_names"] == ["site_id", "checked_at"]
        assert index.get("column_sorting") == {"checked_at": ("desc",)}

        [fk] = inspector.get_foreign_keys("checks")
        assert fk["referred_table"] == "sites"
        assert fk["options"].get("ondelete") == "CASCADE"
    finally:
        engine.dispose()

    command.downgrade(config, "base")
    assert table_names(database_url).isdisjoint({"sites", "checks"})

    command.upgrade(config, "head")
    assert {"sites", "checks"} <= table_names(database_url)


def test_models_match_migrations(database_url: URL) -> None:
    config = alembic_config(database_url)
    command.upgrade(config, "head")

    # Fails if a model change has no matching migration.
    command.check(config)


def test_deleting_a_site_deletes_its_checks(database_url: URL) -> None:
    command.upgrade(alembic_config(database_url), "head")
    engine = create_engine(database_url)
    try:
        with engine.begin() as conn:
            site_id: int = conn.execute(
                text(
                    "INSERT INTO sites (name, url) "
                    "VALUES ('example', 'https://cascade.example.com') RETURNING id"
                )
            ).scalar_one()
            conn.execute(
                text("INSERT INTO checks (site_id, ok) VALUES (:site_id, true)"),
                {"site_id": site_id},
            )
            conn.execute(text("DELETE FROM sites WHERE id = :site_id"), {"site_id": site_id})
            remaining: int = conn.execute(
                text("SELECT count(*) FROM checks WHERE site_id = :site_id"),
                {"site_id": site_id},
            ).scalar_one()
        assert remaining == 0
    finally:
        engine.dispose()

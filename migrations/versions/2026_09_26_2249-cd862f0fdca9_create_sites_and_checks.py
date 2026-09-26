"""create sites and checks

Revision ID: cd862f0fdca9
Revises:
Create Date: 2026-09-26 22:49:47.253453
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "cd862f0fdca9"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sites",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), server_default="60", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 200", name=op.f("ck_sites_name_length")
        ),
        sa.CheckConstraint("char_length(url) <= 2048", name=op.f("ck_sites_url_length")),
        sa.CheckConstraint("interval_seconds > 0", name=op.f("ck_sites_interval_positive")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sites")),
        sa.UniqueConstraint("url", name=op.f("uq_sites_url")),
    )
    op.create_table(
        "checks",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("site_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("status_code", sa.SmallInteger(), nullable=True),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "response_time_ms >= 0", name=op.f("ck_checks_response_time_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["site_id"],
            ["sites.id"],
            name=op.f("fk_checks_site_id_sites"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_checks")),
    )
    op.create_index(
        "ix_checks_site_id_checked_at",
        "checks",
        ["site_id", sa.literal_column("checked_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_checks_site_id_checked_at", table_name="checks")
    op.drop_table("checks")
    op.drop_table("sites")

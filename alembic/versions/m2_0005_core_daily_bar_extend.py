"""m2_0005_core_daily_bar_extend

Revision ID: m2_0005_core_daily_bar_extend
Revises: m2_0004_core_theme_tables
Create Date: 2026-04-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "m2_0005_core_daily_bar_extend"
down_revision = "m2_0004_core_theme_tables"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(col["name"] == column_name for col in columns)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_column("core_daily_bar", "price_adjust_type"):
        op.add_column("core_daily_bar", sa.Column("price_adjust_type", sa.String(length=16), nullable=True))
        bind.execute(sa.text("UPDATE core_daily_bar SET price_adjust_type = 'RAW' WHERE price_adjust_type IS NULL"))
        op.alter_column("core_daily_bar", "price_adjust_type", existing_type=sa.String(length=16), nullable=False)

    if not _has_column("core_daily_bar", "pre_close"):
        op.add_column("core_daily_bar", sa.Column("pre_close", sa.Numeric(20, 6), nullable=True))

    if not _has_column("core_daily_bar", "source_provider"):
        op.add_column("core_daily_bar", sa.Column("source_provider", sa.String(length=32), nullable=True))

    if not _has_column("core_daily_bar", "data_version_id"):
        op.add_column("core_daily_bar", sa.Column("data_version_id", sa.BigInteger(), nullable=True))

    if not _has_column("core_daily_bar", "created_at"):
        op.add_column("core_daily_bar", sa.Column("created_at", sa.DateTime(timezone=False), nullable=True))

    if not _has_column("core_daily_bar", "updated_at"):
        op.add_column("core_daily_bar", sa.Column("updated_at", sa.DateTime(timezone=False), nullable=True))

    unique_constraints = {uc["name"] for uc in inspector.get_unique_constraints("core_daily_bar")}
    indexes = {idx["name"] for idx in inspector.get_indexes("core_daily_bar")}

    if "uq_core_daily_bar_instrument_date_adj" not in unique_constraints:
        op.create_unique_constraint(
            "uq_core_daily_bar_instrument_date_adj",
            "core_daily_bar",
            ["instrument_id", "trade_date", "price_adjust_type"],
        )

    if "ix_core_daily_bar_trade_date" not in indexes:
        op.create_index("ix_core_daily_bar_trade_date", "core_daily_bar", ["trade_date"])

    if "ix_core_daily_bar_source_provider" not in indexes:
        op.create_index("ix_core_daily_bar_source_provider", "core_daily_bar", ["source_provider"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    indexes = {idx["name"] for idx in inspector.get_indexes("core_daily_bar")}
    unique_constraints = {uc["name"] for uc in inspector.get_unique_constraints("core_daily_bar")}

    if "ix_core_daily_bar_source_provider" in indexes:
        op.drop_index("ix_core_daily_bar_source_provider", table_name="core_daily_bar")

    if "ix_core_daily_bar_trade_date" in indexes:
        op.drop_index("ix_core_daily_bar_trade_date", table_name="core_daily_bar")

    if "uq_core_daily_bar_instrument_date_adj" in unique_constraints:
        op.drop_constraint("uq_core_daily_bar_instrument_date_adj", "core_daily_bar", type_="unique")

    if _has_column("core_daily_bar", "updated_at"):
        op.drop_column("core_daily_bar", "updated_at")

    if _has_column("core_daily_bar", "created_at"):
        op.drop_column("core_daily_bar", "created_at")

    if _has_column("core_daily_bar", "data_version_id"):
        op.drop_column("core_daily_bar", "data_version_id")

    if _has_column("core_daily_bar", "source_provider"):
        op.drop_column("core_daily_bar", "source_provider")

    if _has_column("core_daily_bar", "pre_close"):
        op.drop_column("core_daily_bar", "pre_close")

    if _has_column("core_daily_bar", "price_adjust_type"):
        op.drop_column("core_daily_bar", "price_adjust_type")
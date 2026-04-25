"""m2_0004_core_theme_tables

Revision ID: m2_0004_core_theme_tables
Revises: m2_0003_ops_data_sync_tables
Create Date: 2026-04-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "m2_0004_core_theme_tables"
down_revision = "m2_0003_ops_data_sync_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fundamental_snapshot",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("instrument_id", sa.BigInteger(), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("snapshot_type", sa.String(length=32), nullable=False),
        sa.Column("pe_ttm", sa.Numeric(20, 6), nullable=True),
        sa.Column("pb", sa.Numeric(20, 6), nullable=True),
        sa.Column("ps_ttm", sa.Numeric(20, 6), nullable=True),
        sa.Column("dv_ttm", sa.Numeric(20, 6), nullable=True),
        sa.Column("total_mv", sa.Numeric(24, 6), nullable=True),
        sa.Column("circ_mv", sa.Numeric(24, 6), nullable=True),
        sa.Column("roe", sa.Numeric(20, 6), nullable=True),
        sa.Column("roa", sa.Numeric(20, 6), nullable=True),
        sa.Column("gross_margin", sa.Numeric(20, 6), nullable=True),
        sa.Column("net_profit_yoy", sa.Numeric(20, 6), nullable=True),
        sa.Column("report_period", sa.Date(), nullable=True),
        sa.Column("announcement_date", sa.Date(), nullable=True),
        sa.Column("source_provider", sa.String(length=32), nullable=False),
        sa.Column("data_version_id", sa.BigInteger(), nullable=True),
        sa.UniqueConstraint(
            "instrument_id", "trade_date", "snapshot_type",
            name="uq_fundamental_snapshot_inst_date_type"
        ),
    )

    op.create_table(
        "tag",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tag_type", sa.String(length=32), nullable=False),
        sa.Column("tag_code", sa.String(length=64), nullable=False),
        sa.Column("tag_name", sa.String(length=128), nullable=False),
        sa.Column("taxonomy_source", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("tag_type", "tag_code", name="uq_tag_type_code"),
    )

    op.create_table(
        "instrument_tag",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("instrument_id", sa.BigInteger(), nullable=False),
        sa.Column("tag_id", sa.BigInteger(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("source_provider", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Numeric(8, 4), nullable=True),
        sa.UniqueConstraint(
            "instrument_id", "tag_id", "effective_from",
            name="uq_instrument_tag_inst_tag_from"
        ),
    )

    op.create_table(
        "market_index",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("index_code", sa.String(length=64), nullable=False),
        sa.Column("index_name", sa.String(length=128), nullable=False),
        sa.Column("exchange_code", sa.String(length=16), nullable=False),
        sa.Column("index_type", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("index_code", name="uq_market_index_code"),
    )

    op.create_table(
        "market_index_bar",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("market_index_id", sa.BigInteger(), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(20, 6), nullable=True),
        sa.Column("high", sa.Numeric(20, 6), nullable=True),
        sa.Column("low", sa.Numeric(20, 6), nullable=True),
        sa.Column("close", sa.Numeric(20, 6), nullable=False),
        sa.Column("volume", sa.Numeric(24, 6), nullable=True),
        sa.Column("turnover", sa.Numeric(24, 6), nullable=True),
        sa.Column("source_provider", sa.String(length=32), nullable=False),
        sa.Column("data_version_id", sa.BigInteger(), nullable=True),
        sa.UniqueConstraint("market_index_id", "trade_date", name="uq_market_index_bar_idx_date"),
    )

    op.create_table(
        "market_breadth",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("exchange_code", sa.String(length=16), nullable=False),
        sa.Column("universe_code", sa.String(length=32), nullable=False),
        sa.Column("advance_count", sa.Integer(), nullable=True),
        sa.Column("decline_count", sa.Integer(), nullable=True),
        sa.Column("flat_count", sa.Integer(), nullable=True),
        sa.Column("limit_up_count", sa.Integer(), nullable=True),
        sa.Column("limit_down_count", sa.Integer(), nullable=True),
        sa.Column("suspended_count", sa.Integer(), nullable=True),
        sa.Column("source_provider", sa.String(length=32), nullable=False),
        sa.Column("data_version_id", sa.BigInteger(), nullable=True),
        sa.UniqueConstraint(
            "trade_date", "exchange_code", "universe_code",
            name="uq_market_breadth_date_ex_universe"
        ),
    )


def downgrade() -> None:
    op.drop_table("market_breadth")
    op.drop_table("market_index_bar")
    op.drop_table("market_index")
    op.drop_table("instrument_tag")
    op.drop_table("tag")
    op.drop_table("fundamental_snapshot")
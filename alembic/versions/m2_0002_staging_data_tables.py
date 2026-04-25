"""m2_0002_staging_data_tables

Revision ID: m2_0002_staging_data_tables
Revises: m2_0001_raw_data_tables
Create Date: 2026-04-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "m2_0002_staging_data_tables"
down_revision = "m2_0001_raw_data_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stg_daily_bar",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("sync_run_id", sa.BigInteger(), nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("provider_name", sa.String(length=32), nullable=False),
        sa.Column("dataset_code", sa.String(length=64), nullable=False),
        sa.Column("market_code", sa.String(length=16), nullable=False),
        sa.Column("exchange_code", sa.String(length=16), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("vendor_symbol", sa.String(length=64), nullable=True),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("price_adjust_type", sa.String(length=16), nullable=False),
        sa.Column("open", sa.Numeric(20, 6), nullable=True),
        sa.Column("high", sa.Numeric(20, 6), nullable=True),
        sa.Column("low", sa.Numeric(20, 6), nullable=True),
        sa.Column("close", sa.Numeric(20, 6), nullable=True),
        sa.Column("pre_close", sa.Numeric(20, 6), nullable=True),
        sa.Column("volume", sa.Numeric(24, 6), nullable=True),
        sa.Column("turnover", sa.Numeric(24, 6), nullable=True),
        sa.Column("amplitude", sa.Numeric(18, 8), nullable=True),
        sa.Column("pct_change", sa.Numeric(18, 8), nullable=True),
        sa.Column("price_change", sa.Numeric(18, 8), nullable=True),
        sa.Column("turnover_rate", sa.Numeric(18, 8), nullable=True),
        sa.Column("suspended_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("provider_record_key", sa.String(length=256), nullable=False),
        sa.Column("raw_record_id", sa.BigInteger(), nullable=True),
        sa.UniqueConstraint(
            "provider_name", "ticker", "trade_date", "price_adjust_type",
            name="uq_stg_daily_bar_provider_ticker_date_adj"
        ),
    )
    op.create_index("ix_stg_daily_bar_ticker_trade_date", "stg_daily_bar", ["ticker", "trade_date"])
    op.create_index("ix_stg_daily_bar_batch_id", "stg_daily_bar", ["batch_id"])


def downgrade() -> None:
    op.drop_index("ix_stg_daily_bar_batch_id", table_name="stg_daily_bar")
    op.drop_index("ix_stg_daily_bar_ticker_trade_date", table_name="stg_daily_bar")
    op.drop_table("stg_daily_bar")
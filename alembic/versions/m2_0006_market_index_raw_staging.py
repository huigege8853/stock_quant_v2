"""m2_0006_market_index_raw_staging

Revision ID: m2_0006_market_index_raw_staging
Revises: m2_0005_core_daily_bar_extend
Create Date: 2026-04-08 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "m2_0006_market_index_raw_staging"
down_revision = "m2_0005_core_daily_bar_extend"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if not _has_table("raw_market_index"):
        op.create_table(
            "raw_market_index",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("provider_name", sa.String(length=32), nullable=False),
            sa.Column("dataset_code", sa.String(length=64), nullable=False),
            sa.Column("provider_record_key", sa.String(length=256), nullable=False),
            sa.Column("symbol", sa.String(length=64), nullable=True),
            sa.Column("trade_date", sa.Date(), nullable=True),
            sa.Column("batch_id", sa.BigInteger(), nullable=False),
            sa.Column("sync_run_id", sa.BigInteger(), nullable=False),
            sa.Column("request_params", sa.JSON(), nullable=True),
            sa.Column("payload_json", sa.JSON(), nullable=False),
            sa.Column("payload_hash", sa.String(length=64), nullable=False),
            sa.Column("provider_update_ts", sa.DateTime(timezone=False), nullable=True),
            sa.Column("ingested_at", sa.DateTime(timezone=False), nullable=False),
            sa.UniqueConstraint(
                "provider_name",
                "dataset_code",
                "provider_record_key",
                name="uq_raw_market_index_provider_key",
            ),
        )
        op.create_index("ix_raw_market_index_symbol_trade_date", "raw_market_index", ["symbol", "trade_date"])
        op.create_index("ix_raw_market_index_batch_id", "raw_market_index", ["batch_id"])
        op.create_index("ix_raw_market_index_sync_run_id", "raw_market_index", ["sync_run_id"])

    if not _has_table("stg_market_index"):
        op.create_table(
            "stg_market_index",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("sync_run_id", sa.BigInteger(), nullable=False),
            sa.Column("batch_id", sa.BigInteger(), nullable=False),
            sa.Column("provider_name", sa.String(length=32), nullable=False),
            sa.Column("dataset_code", sa.String(length=64), nullable=False),
            sa.Column("index_code", sa.String(length=64), nullable=False),
            sa.Column("exchange_code", sa.String(length=16), nullable=False),
            sa.Column("index_name", sa.String(length=128), nullable=True),
            sa.Column("index_type", sa.String(length=32), nullable=True),
            sa.Column("trade_date", sa.Date(), nullable=False),
            sa.Column("open", sa.Numeric(20, 6), nullable=True),
            sa.Column("high", sa.Numeric(20, 6), nullable=True),
            sa.Column("low", sa.Numeric(20, 6), nullable=True),
            sa.Column("close", sa.Numeric(20, 6), nullable=True),
            sa.Column("volume", sa.Numeric(24, 6), nullable=True),
            sa.Column("turnover", sa.Numeric(24, 6), nullable=True),
            sa.Column("provider_record_key", sa.String(length=256), nullable=False),
            sa.Column("raw_record_id", sa.BigInteger(), nullable=True),
            sa.UniqueConstraint(
                "provider_name",
                "index_code",
                "trade_date",
                name="uq_stg_market_index_provider_code_date",
            ),
        )
        op.create_index("ix_stg_market_index_code_trade_date", "stg_market_index", ["index_code", "trade_date"])
        op.create_index("ix_stg_market_index_batch_id", "stg_market_index", ["batch_id"])


def downgrade() -> None:
    if _has_table("stg_market_index"):
        op.drop_index("ix_stg_market_index_batch_id", table_name="stg_market_index")
        op.drop_index("ix_stg_market_index_code_trade_date", table_name="stg_market_index")
        op.drop_table("stg_market_index")

    if _has_table("raw_market_index"):
        op.drop_index("ix_raw_market_index_sync_run_id", table_name="raw_market_index")
        op.drop_index("ix_raw_market_index_batch_id", table_name="raw_market_index")
        op.drop_index("ix_raw_market_index_symbol_trade_date", table_name="raw_market_index")
        op.drop_table("raw_market_index")

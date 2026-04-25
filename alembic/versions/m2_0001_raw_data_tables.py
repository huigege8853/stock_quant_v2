"""m2_0001_raw_data_tables

Revision ID: m2_0001_raw_data_tables
Revises: m1_0005_core_market_data
Create Date: 2026-04-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "m2_0001_raw_data_tables"
down_revision = "m1_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "raw_daily_bar",
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
            "provider_name", "dataset_code", "provider_record_key",
            name="uq_raw_daily_bar_provider_key"
        ),
    )
    op.create_index("ix_raw_daily_bar_symbol_trade_date", "raw_daily_bar", ["symbol", "trade_date"])
    op.create_index("ix_raw_daily_bar_batch_id", "raw_daily_bar", ["batch_id"])
    op.create_index("ix_raw_daily_bar_sync_run_id", "raw_daily_bar", ["sync_run_id"])


def downgrade() -> None:
    op.drop_index("ix_raw_daily_bar_sync_run_id", table_name="raw_daily_bar")
    op.drop_index("ix_raw_daily_bar_batch_id", table_name="raw_daily_bar")
    op.drop_index("ix_raw_daily_bar_symbol_trade_date", table_name="raw_daily_bar")
    op.drop_table("raw_daily_bar")
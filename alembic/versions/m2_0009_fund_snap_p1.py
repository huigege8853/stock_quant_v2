"""m2_0009_fund_snap_p1

Revision ID: m2_0009_fund_snap_p1
Revises: m2_0008_adj_factor_tbls
Create Date: 2026-04-15 10:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "m2_0009_fund_snap_p1"
down_revision = "m2_0008_adj_factor_tbls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "raw_fundamental_snapshot",
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
            name="uq_raw_fundamental_snapshot_key",
        ),
    )
    op.create_index(
        "ix_raw_fund_snapshot_sym_dt",
        "raw_fundamental_snapshot",
        ["symbol", "trade_date"],
    )
    op.create_index(
        "ix_raw_fund_snapshot_bid",
        "raw_fundamental_snapshot",
        ["batch_id"],
    )
    op.create_index(
        "ix_raw_fund_snapshot_sid",
        "raw_fundamental_snapshot",
        ["sync_run_id"],
    )

    op.create_table(
        "stg_fundamental_snapshot",
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
        sa.Column("provider_record_key", sa.String(length=256), nullable=False),
        sa.Column("raw_record_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["raw_record_id"],
            ["raw_fundamental_snapshot.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "provider_name",
            "ticker",
            "trade_date",
            "snapshot_type",
            name="uq_stg_fundamental_snapshot_key",
        ),
    )
    op.create_index(
        "ix_stg_fund_snapshot_dt",
        "stg_fundamental_snapshot",
        ["trade_date"],
    )
    op.create_index(
        "ix_stg_fund_snapshot_bid",
        "stg_fundamental_snapshot",
        ["batch_id"],
    )
    op.create_index(
        "ix_stg_fund_snapshot_sid",
        "stg_fundamental_snapshot",
        ["sync_run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_stg_fund_snapshot_sid", table_name="stg_fundamental_snapshot")
    op.drop_index("ix_stg_fund_snapshot_bid", table_name="stg_fundamental_snapshot")
    op.drop_index("ix_stg_fund_snapshot_dt", table_name="stg_fundamental_snapshot")
    op.drop_table("stg_fundamental_snapshot")

    op.drop_index("ix_raw_fund_snapshot_sid", table_name="raw_fundamental_snapshot")
    op.drop_index("ix_raw_fund_snapshot_bid", table_name="raw_fundamental_snapshot")
    op.drop_index("ix_raw_fund_snapshot_sym_dt", table_name="raw_fundamental_snapshot")
    op.drop_table("raw_fundamental_snapshot")
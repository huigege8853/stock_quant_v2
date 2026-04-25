"""m2_0008_adj_factor_tbls

Revision ID: m2_0008_adj_factor_tbls
Revises: m2_0007_core_mb_p1
Create Date: 2026-04-10 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "m2_0008_adj_factor_tbls"
down_revision = "m2_0007_core_mb_p1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "raw_adjust_factor",
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
            name="uq_raw_adjfac_key",
        ),
    )
    op.create_index(
        "ix_raw_adjfac_sym_dt",
        "raw_adjust_factor",
        ["symbol", "trade_date"],
    )
    op.create_index(
        "ix_raw_adjfac_bid",
        "raw_adjust_factor",
        ["batch_id"],
    )
    op.create_index(
        "ix_raw_adjfac_sid",
        "raw_adjust_factor",
        ["sync_run_id"],
    )

    op.create_table(
        "stg_adjust_factor",
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
        sa.Column("adjust_factor", sa.Numeric(20, 8), nullable=True),
        sa.Column("provider_record_key", sa.String(length=256), nullable=False),
        sa.Column("raw_record_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["raw_record_id"],
            ["raw_adjust_factor.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "provider_name",
            "ticker",
            "trade_date",
            name="uq_stg_adjfac_key",
        ),
    )
    op.create_index(
        "ix_stg_adjfac_dt",
        "stg_adjust_factor",
        ["trade_date"],
    )
    op.create_index(
        "ix_stg_adjfac_bid",
        "stg_adjust_factor",
        ["batch_id"],
    )
    op.create_index(
        "ix_stg_adjfac_sid",
        "stg_adjust_factor",
        ["sync_run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_stg_adjfac_sid", table_name="stg_adjust_factor")
    op.drop_index("ix_stg_adjfac_bid", table_name="stg_adjust_factor")
    op.drop_index("ix_stg_adjfac_dt", table_name="stg_adjust_factor")
    op.drop_table("stg_adjust_factor")

    op.drop_index("ix_raw_adjfac_sid", table_name="raw_adjust_factor")
    op.drop_index("ix_raw_adjfac_bid", table_name="raw_adjust_factor")
    op.drop_index("ix_raw_adjfac_sym_dt", table_name="raw_adjust_factor")
    op.drop_table("raw_adjust_factor")
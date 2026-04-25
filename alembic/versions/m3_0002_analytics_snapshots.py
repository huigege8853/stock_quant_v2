"""m3_0002_analytics_snapshots

Revision ID: m3_0002_analytics_snapshots
Revises: m3_0001_analytics_definitions
Create Date: 2026-04-16 12:10:00
"""

from alembic import op
import sqlalchemy as sa


revision = "m3_0002_analytics_snapshots"
down_revision = "m3_0001_analytics_definitions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analytics_instrument_indicator_snapshot",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("instrument_id", sa.BigInteger(), nullable=False),
        sa.Column("indicator_code", sa.String(length=64), nullable=False),
        sa.Column("definition_version", sa.String(length=32), nullable=False),
        sa.Column("value_numeric", sa.Numeric(24, 10), nullable=True),
        sa.Column("value_text", sa.String(length=128), nullable=True),
        sa.Column("is_ready", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("warmup_ready", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("data_version_id", sa.BigInteger(), nullable=True),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["instrument_id"], ["meta_instrument.id"], name="fk_aiis__instrument_id__meta_instrument"),
        sa.ForeignKeyConstraint(["run_id"], ["ops_run.id"], name="fk_aiis__run_id__ops_run"),
        sa.UniqueConstraint(
            "trade_date",
            "instrument_id",
            "indicator_code",
            "definition_version",
            name="uq_aiis__date_instr_code_ver",
        ),
    )
    op.create_index("ix_aiis__trade_date_indicator_code", "analytics_instrument_indicator_snapshot", ["trade_date", "indicator_code"])
    op.create_index("ix_aiis__instrument_id_trade_date", "analytics_instrument_indicator_snapshot", ["instrument_id", "trade_date"])
    op.create_index("ix_aiis__run_id", "analytics_instrument_indicator_snapshot", ["run_id"])

    op.create_table(
        "analytics_instrument_factor_snapshot",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("instrument_id", sa.BigInteger(), nullable=False),
        sa.Column("factor_code", sa.String(length=64), nullable=False),
        sa.Column("definition_version", sa.String(length=32), nullable=False),
        sa.Column("raw_value", sa.Numeric(24, 10), nullable=True),
        sa.Column("winsorized_value", sa.Numeric(24, 10), nullable=True),
        sa.Column("standardized_value", sa.Numeric(24, 10), nullable=True),
        sa.Column("rank_value", sa.Numeric(24, 10), nullable=True),
        sa.Column("bucket_value", sa.String(length=32), nullable=True),
        sa.Column("is_ready", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("data_version_id", sa.BigInteger(), nullable=True),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["instrument_id"], ["meta_instrument.id"], name="fk_aifs__instrument_id__meta_instrument"),
        sa.ForeignKeyConstraint(["run_id"], ["ops_run.id"], name="fk_aifs__run_id__ops_run"),
        sa.UniqueConstraint(
            "trade_date",
            "instrument_id",
            "factor_code",
            "definition_version",
            name="uq_aifs__date_instr_code_ver",
        ),
    )
    op.create_index("ix_aifs__trade_date_factor_code", "analytics_instrument_factor_snapshot", ["trade_date", "factor_code"])
    op.create_index("ix_aifs__instrument_id_trade_date", "analytics_instrument_factor_snapshot", ["instrument_id", "trade_date"])
    op.create_index("ix_aifs__run_id", "analytics_instrument_factor_snapshot", ["run_id"])

    op.create_table(
        "analytics_feature_snapshot",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("instrument_id", sa.BigInteger(), nullable=False),
        sa.Column("feature_code", sa.String(length=64), nullable=False),
        sa.Column("feature_set_code", sa.String(length=64), nullable=False),
        sa.Column("feature_set_version", sa.String(length=32), nullable=False),
        sa.Column("feature_value_numeric", sa.Numeric(24, 10), nullable=True),
        sa.Column("feature_value_text", sa.String(length=128), nullable=True),
        sa.Column("is_imputed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("impute_method", sa.String(length=32), nullable=True),
        sa.Column("scaling_applied", sa.String(length=32), nullable=True),
        sa.Column("sample_status", sa.String(length=32), nullable=False, server_default="ready"),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["instrument_id"], ["meta_instrument.id"], name="fk_afs__instrument_id__meta_instrument"),
        sa.ForeignKeyConstraint(["run_id"], ["ops_run.id"], name="fk_afs__run_id__ops_run"),
        sa.UniqueConstraint(
            "trade_date",
            "instrument_id",
            "feature_code",
            "feature_set_code",
            "feature_set_version",
            name="uq_afs__date_instr_feature_set_ver",
        ),
    )
    op.create_index("ix_afs__trade_date_feature_set_code", "analytics_feature_snapshot", ["trade_date", "feature_set_code"])
    op.create_index("ix_afs__instrument_id_trade_date", "analytics_feature_snapshot", ["instrument_id", "trade_date"])
    op.create_index("ix_afs__run_id", "analytics_feature_snapshot", ["run_id"])

    op.create_table(
        "analytics_label_snapshot",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("anchor_date", sa.Date(), nullable=False),
        sa.Column("instrument_id", sa.BigInteger(), nullable=False),
        sa.Column("label_code", sa.String(length=64), nullable=False),
        sa.Column("definition_version", sa.String(length=32), nullable=False),
        sa.Column("label_value_numeric", sa.Numeric(24, 10), nullable=True),
        sa.Column("label_value_class", sa.String(length=32), nullable=True),
        sa.Column("horizon_end_date", sa.Date(), nullable=False),
        sa.Column("is_censored", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("leakage_checked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["instrument_id"], ["meta_instrument.id"], name="fk_als__instrument_id__meta_instrument"),
        sa.ForeignKeyConstraint(["run_id"], ["ops_run.id"], name="fk_als__run_id__ops_run"),
        sa.UniqueConstraint(
            "anchor_date",
            "instrument_id",
            "label_code",
            "definition_version",
            name="uq_als__date_instr_code_ver",
        ),
    )
    op.create_index("ix_als__anchor_date_label_code", "analytics_label_snapshot", ["anchor_date", "label_code"])
    op.create_index("ix_als__instrument_id_anchor_date", "analytics_label_snapshot", ["instrument_id", "anchor_date"])
    op.create_index("ix_als__run_id", "analytics_label_snapshot", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_als__run_id", table_name="analytics_label_snapshot")
    op.drop_index("ix_als__instrument_id_anchor_date", table_name="analytics_label_snapshot")
    op.drop_index("ix_als__anchor_date_label_code", table_name="analytics_label_snapshot")
    op.drop_table("analytics_label_snapshot")

    op.drop_index("ix_afs__run_id", table_name="analytics_feature_snapshot")
    op.drop_index("ix_afs__instrument_id_trade_date", table_name="analytics_feature_snapshot")
    op.drop_index("ix_afs__trade_date_feature_set_code", table_name="analytics_feature_snapshot")
    op.drop_table("analytics_feature_snapshot")

    op.drop_index("ix_aifs__run_id", table_name="analytics_instrument_factor_snapshot")
    op.drop_index("ix_aifs__instrument_id_trade_date", table_name="analytics_instrument_factor_snapshot")
    op.drop_index("ix_aifs__trade_date_factor_code", table_name="analytics_instrument_factor_snapshot")
    op.drop_table("analytics_instrument_factor_snapshot")

    op.drop_index("ix_aiis__run_id", table_name="analytics_instrument_indicator_snapshot")
    op.drop_index("ix_aiis__instrument_id_trade_date", table_name="analytics_instrument_indicator_snapshot")
    op.drop_index("ix_aiis__trade_date_indicator_code", table_name="analytics_instrument_indicator_snapshot")
    op.drop_table("analytics_instrument_indicator_snapshot")
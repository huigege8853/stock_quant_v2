"""m3_0001_analytics_definitions

Revision ID: m3_0001_analytics_definitions
Revises: m2_0009_fund_snap_p1
Create Date: 2026-04-16 12:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "m3_0001_analytics_definitions"
down_revision = "m2_0009_fund_snap_p1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "meta_indicator_definition",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("indicator_code", sa.String(length=64), nullable=False),
        sa.Column("indicator_name", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("input_topic", sa.String(length=64), nullable=False),
        sa.Column("input_fields_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("formula_expr", sa.Text(), nullable=True),
        sa.Column("window_size", sa.Integer(), nullable=True),
        sa.Column("warmup_bars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("price_adjust_type", sa.String(length=32), nullable=False, server_default="forward_adj"),
        sa.Column("publish_lag_days", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("null_policy", sa.String(length=32), nullable=False, server_default="keep_null"),
        sa.Column("value_type", sa.String(length=32), nullable=False, server_default="numeric"),
        sa.Column("version", sa.String(length=32), nullable=False, server_default="v1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.UniqueConstraint("indicator_code", "version", name="uq_meta_indicator_definition__code_version"),
    )

    op.create_table(
        "meta_factor_definition",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("factor_code", sa.String(length=64), nullable=False),
        sa.Column("factor_name", sa.String(length=128), nullable=False),
        sa.Column("factor_family", sa.String(length=64), nullable=False),
        sa.Column("base_indicator_codes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("transform_pipeline_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("cross_sectional_scope", sa.String(length=64), nullable=False, server_default="all_a_share"),
        sa.Column("winsorize_method", sa.String(length=32), nullable=True),
        sa.Column("standardize_method", sa.String(length=32), nullable=True),
        sa.Column("neutralize_method", sa.String(length=32), nullable=True),
        sa.Column("warmup_bars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("publish_lag_days", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("value_type", sa.String(length=32), nullable=False, server_default="numeric"),
        sa.Column("version", sa.String(length=32), nullable=False, server_default="v1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.UniqueConstraint("factor_code", "version", name="uq_meta_factor_definition__code_version"),
    )

    op.create_table(
        "meta_feature_definition",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("feature_code", sa.String(length=64), nullable=False),
        sa.Column("feature_name", sa.String(length=128), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_ref_code", sa.String(length=64), nullable=False),
        sa.Column("dtype", sa.String(length=32), nullable=False, server_default="float64"),
        sa.Column("fillna_policy", sa.String(length=32), nullable=False, server_default="none"),
        sa.Column("scaling_policy", sa.String(length=32), nullable=False, server_default="none"),
        sa.Column("winsorize_policy", sa.String(length=32), nullable=False, server_default="none"),
        sa.Column("availability_rule_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("version", sa.String(length=32), nullable=False, server_default="v1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.UniqueConstraint("feature_code", "version", name="uq_meta_feature_definition__code_version"),
    )

    op.create_table(
        "meta_feature_set_definition",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("feature_set_code", sa.String(length=64), nullable=False),
        sa.Column("feature_set_name", sa.String(length=128), nullable=False),
        sa.Column("universe_rule_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("feature_codes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("join_keys_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[\"trade_date\",\"instrument_id\"]'::jsonb")),
        sa.Column("sample_filter_rule_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("standardization_rule_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("label_codes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("train_serving_contract_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("version", sa.String(length=32), nullable=False, server_default="v1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.UniqueConstraint("feature_set_code", "version", name="uq_meta_feature_set_definition__code_version"),
    )

    op.create_table(
        "meta_label_definition",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("label_code", sa.String(length=64), nullable=False),
        sa.Column("label_name", sa.String(length=128), nullable=False),
        sa.Column("label_type", sa.String(length=32), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("target_expr", sa.Text(), nullable=False),
        sa.Column("price_basis", sa.String(length=32), nullable=False, server_default="adj_close"),
        sa.Column("barrier_rule_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("publish_lag_days", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("leakage_guard_rule_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("version", sa.String(length=32), nullable=False, server_default="v1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.UniqueConstraint("label_code", "version", name="uq_meta_label_definition__code_version"),
    )


def downgrade() -> None:
    op.drop_table("meta_label_definition")
    op.drop_table("meta_feature_set_definition")
    op.drop_table("meta_feature_definition")
    op.drop_table("meta_factor_definition")
    op.drop_table("meta_indicator_definition")
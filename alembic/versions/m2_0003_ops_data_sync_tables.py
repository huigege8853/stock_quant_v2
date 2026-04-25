"""m2_0003_ops_data_sync_tables

Revision ID: m2_0003_ops_data_sync_tables
Revises: m2_0002_staging_data_tables
Create Date: 2026-04-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "m2_0003_ops_data_sync_tables"
down_revision = "m2_0002_staging_data_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_sync_run",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("sync_job_code", sa.String(length=64), nullable=False),
        sa.Column("theme_code", sa.String(length=64), nullable=False),
        sa.Column("dataset_code", sa.String(length=64), nullable=False),
        sa.Column("provider_name", sa.String(length=32), nullable=False),
        sa.Column("sync_mode", sa.String(length=32), nullable=False),
        sa.Column("sync_granularity", sa.String(length=32), nullable=False),
        sa.Column("partition_from", sa.Date(), nullable=True),
        sa.Column("partition_to", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("cursor_json", sa.JSON(), nullable=True),
        sa.Column("request_params", sa.JSON(), nullable=True),
        sa.Column("stats_json", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=False), nullable=True),
    )
    op.create_index("ix_data_sync_run_run_id", "data_sync_run", ["run_id"])
    op.create_index("ix_data_sync_run_job_status", "data_sync_run", ["sync_job_code", "status"])
    op.create_index("ix_data_sync_run_theme_provider", "data_sync_run", ["theme_code", "provider_name"])

    op.create_table(
        "data_batch",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("data_sync_run_id", sa.BigInteger(), nullable=False),
        sa.Column("batch_no", sa.Integer(), nullable=False),
        sa.Column("batch_key", sa.String(length=128), nullable=False),
        sa.Column("batch_type", sa.String(length=32), nullable=False),
        sa.Column("partition_date", sa.Date(), nullable=True),
        sa.Column("partition_symbol", sa.String(length=64), nullable=True),
        sa.Column("page_no", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_rows", sa.Integer(), nullable=True),
        sa.Column("raw_rows", sa.Integer(), nullable=True),
        sa.Column("staging_rows", sa.Integer(), nullable=True),
        sa.Column("core_upsert_rows", sa.Integer(), nullable=True),
        sa.Column("error_rows", sa.Integer(), nullable=True),
        sa.Column("checkpoint_json", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=False), nullable=True),
    )
    op.create_index("ix_data_batch_run_id", "data_batch", ["data_sync_run_id"])
    op.create_index("ix_data_batch_status", "data_batch", ["status"])

    op.create_table(
        "data_quality_issue",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("data_sync_run_id", sa.BigInteger(), nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=True),
        sa.Column("theme_code", sa.String(length=64), nullable=False),
        sa.Column("dataset_code", sa.String(length=64), nullable=False),
        sa.Column("layer_code", sa.String(length=16), nullable=False),
        sa.Column("issue_code", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("business_key", sa.String(length=256), nullable=True),
        sa.Column("provider_name", sa.String(length=32), nullable=True),
        sa.Column("trade_date", sa.Date(), nullable=True),
        sa.Column("symbol", sa.String(length=64), nullable=True),
        sa.Column("record_ref", sa.JSON(), nullable=True),
        sa.Column("issue_detail", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False),
    )
    op.create_index("ix_data_quality_issue_run_id", "data_quality_issue", ["data_sync_run_id"])
    op.create_index("ix_data_quality_issue_theme_code", "data_quality_issue", ["theme_code"])
    op.create_index("ix_data_quality_issue_issue_code", "data_quality_issue", ["issue_code"])

    op.create_table(
        "data_lineage",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("data_sync_run_id", sa.BigInteger(), nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=True),
        sa.Column("theme_code", sa.String(length=64), nullable=False),
        sa.Column("dataset_code", sa.String(length=64), nullable=False),
        sa.Column("source_layer", sa.String(length=16), nullable=False),
        sa.Column("source_table", sa.String(length=128), nullable=False),
        sa.Column("source_record_ref", sa.String(length=256), nullable=False),
        sa.Column("target_layer", sa.String(length=16), nullable=False),
        sa.Column("target_table", sa.String(length=128), nullable=False),
        sa.Column("target_record_ref", sa.String(length=256), nullable=False),
        sa.Column("transform_code", sa.String(length=64), nullable=False),
        sa.Column("transform_version", sa.String(length=64), nullable=False),
        sa.Column("lineage_meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False),
    )
    op.create_index("ix_data_lineage_run_id", "data_lineage", ["data_sync_run_id"])
    op.create_index("ix_data_lineage_source", "data_lineage", ["source_table", "source_record_ref"])
    op.create_index("ix_data_lineage_target", "data_lineage", ["target_table", "target_record_ref"])


def downgrade() -> None:
    op.drop_index("ix_data_lineage_target", table_name="data_lineage")
    op.drop_index("ix_data_lineage_source", table_name="data_lineage")
    op.drop_index("ix_data_lineage_run_id", table_name="data_lineage")
    op.drop_table("data_lineage")

    op.drop_index("ix_data_quality_issue_issue_code", table_name="data_quality_issue")
    op.drop_index("ix_data_quality_issue_theme_code", table_name="data_quality_issue")
    op.drop_index("ix_data_quality_issue_run_id", table_name="data_quality_issue")
    op.drop_table("data_quality_issue")

    op.drop_index("ix_data_batch_status", table_name="data_batch")
    op.drop_index("ix_data_batch_run_id", table_name="data_batch")
    op.drop_table("data_batch")

    op.drop_index("ix_data_sync_run_theme_provider", table_name="data_sync_run")
    op.drop_index("ix_data_sync_run_job_status", table_name="data_sync_run")
    op.drop_index("ix_data_sync_run_run_id", table_name="data_sync_run")
    op.drop_table("data_sync_run")
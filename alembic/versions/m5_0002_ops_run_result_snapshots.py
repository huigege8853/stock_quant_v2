"""m5 ops run result snapshots

Revision ID: m5_0002_ops_run_result_snapshots
Revises: m5_0001_research_core
Create Date: 2026-04-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "m5_0002_ops_run_result_snapshots"
down_revision = "m5_0001_research_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ops_run_metric_snapshot",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("metric_namespace", sa.String(length=64), nullable=False),
        sa.Column("metric_code", sa.String(length=128), nullable=False),
        sa.Column("metric_name", sa.String(length=255), nullable=True),
        sa.Column("metric_value_numeric", sa.Numeric(30, 10), nullable=True),
        sa.Column("metric_value_text", sa.Text(), nullable=True),
        sa.Column(
            "metric_value_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column(
            "dimension_type",
            sa.String(length=64),
            nullable=False,
            server_default="PORTFOLIO",
        ),
        sa.Column(
            "dimension_key",
            sa.String(length=128),
            nullable=False,
            server_default="ALL",
        ),
        sa.Column(
            "sequence_no",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["ops_run.id"],
            name="fk_ops_run_metric__run",
        ),
        sa.UniqueConstraint(
            "run_id",
            "metric_namespace",
            "metric_code",
            "dimension_type",
            "dimension_key",
            "sequence_no",
            name="uq_ops_run_metric__key",
        ),
    )

    op.create_index(
        "ix_ops_run_metric__run_ns",
        "ops_run_metric_snapshot",
        ["run_id", "metric_namespace"],
    )
    op.create_index(
        "ix_ops_run_metric__code",
        "ops_run_metric_snapshot",
        ["metric_code"],
    )
    op.create_index(
        "ix_ops_run_metric__period",
        "ops_run_metric_snapshot",
        ["period_start", "period_end"],
    )

    op.create_table(
        "ops_run_series_snapshot",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("series_namespace", sa.String(length=64), nullable=False),
        sa.Column("series_code", sa.String(length=128), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("instrument_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "dimension_type",
            sa.String(length=64),
            nullable=False,
            server_default="PORTFOLIO",
        ),
        sa.Column(
            "dimension_key",
            sa.String(length=128),
            nullable=False,
            server_default="ALL",
        ),
        sa.Column("value_numeric", sa.Numeric(30, 10), nullable=True),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column(
            "value_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["ops_run.id"],
            name="fk_ops_run_series__run",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["meta_instrument.id"],
            name="fk_ops_run_series__instrument",
        ),
        sa.UniqueConstraint(
            "run_id",
            "series_namespace",
            "series_code",
            "trade_date",
            "dimension_type",
            "dimension_key",
            name="uq_ops_run_series__key",
        ),
    )

    op.create_index(
        "ix_ops_run_series__run_ns",
        "ops_run_series_snapshot",
        ["run_id", "series_namespace"],
    )
    op.create_index(
        "ix_ops_run_series__code_date",
        "ops_run_series_snapshot",
        ["series_code", "trade_date"],
    )
    op.create_index(
        "ix_ops_run_series__instrument",
        "ops_run_series_snapshot",
        ["instrument_id"],
    )

    op.create_table(
        "ops_run_artifact",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("artifact_type", sa.String(length=64), nullable=False),
        sa.Column("artifact_code", sa.String(length=128), nullable=False),
        sa.Column("artifact_name", sa.String(length=255), nullable=True),
        sa.Column("storage_backend", sa.String(length=64), nullable=False),
        sa.Column("uri", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("checksum_sha256", sa.String(length=128), nullable=True),
        sa.Column(
            "payload_schema",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "artifact_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["ops_run.id"],
            name="fk_ops_run_artifact__run",
        ),
        sa.UniqueConstraint(
            "run_id",
            "artifact_code",
            name="uq_ops_run_artifact__code",
        ),
    )

    op.create_index(
        "ix_ops_run_artifact__run",
        "ops_run_artifact",
        ["run_id"],
    )
    op.create_index(
        "ix_ops_run_artifact__type",
        "ops_run_artifact",
        ["artifact_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_ops_run_artifact__type", table_name="ops_run_artifact")
    op.drop_index("ix_ops_run_artifact__run", table_name="ops_run_artifact")
    op.drop_table("ops_run_artifact")

    op.drop_index("ix_ops_run_series__instrument", table_name="ops_run_series_snapshot")
    op.drop_index("ix_ops_run_series__code_date", table_name="ops_run_series_snapshot")
    op.drop_index("ix_ops_run_series__run_ns", table_name="ops_run_series_snapshot")
    op.drop_table("ops_run_series_snapshot")

    op.drop_index("ix_ops_run_metric__period", table_name="ops_run_metric_snapshot")
    op.drop_index("ix_ops_run_metric__code", table_name="ops_run_metric_snapshot")
    op.drop_index("ix_ops_run_metric__run_ns", table_name="ops_run_metric_snapshot")
    op.drop_table("ops_run_metric_snapshot")
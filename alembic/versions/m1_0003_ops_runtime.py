from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "m1_0003"
down_revision = "m1_0002"
branch_labels = None
depends_on = None


def _id_column() -> sa.Column:
    return sa.Column(
        "id",
        sa.BigInteger(),
        sa.Identity(start=1),
        nullable=False,
    )


def _created_at_column() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def _updated_at_column() -> sa.Column:
    return sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "ops_run",
        _id_column(),
        sa.Column("run_uid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_type", sa.String(length=32), nullable=False),
        sa.Column("run_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("trigger_type", sa.String(length=32), nullable=False),
        sa.Column("parent_run_id", sa.BigInteger(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "context_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        _created_at_column(),
        _updated_at_column(),
        sa.ForeignKeyConstraint(
            ["parent_run_id"],
            ["ops_run.id"],
            name="fk_ops_run__parent_run_id__ops_run",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ops_run"),
        sa.UniqueConstraint("run_uid", name="uq_ops_run__run_uid"),
    )
    op.create_index(
        "ix_ops_run__parent_run_id",
        "ops_run",
        ["parent_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_ops_run__run_type_status",
        "ops_run",
        ["run_type", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ops_run__requested_at",
        "ops_run",
        ["requested_at"],
        unique=False,
    )

    op.create_table(
        "ops_run_step",
        _id_column(),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("step_code", sa.String(length=64), nullable=False),
        sa.Column("step_name", sa.String(length=128), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "payload_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        _created_at_column(),
        _updated_at_column(),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["ops_run.id"],
            name="fk_ops_run_step__run_id__ops_run",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ops_run_step"),
        sa.UniqueConstraint(
            "run_id",
            "step_code",
            name="uq_ops_run_step__run_id_step_code",
        ),
    )
    op.create_index(
        "ix_ops_run_step__run_id",
        "ops_run_step",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_ops_run_step__run_id_sequence_no",
        "ops_run_step",
        ["run_id", "sequence_no"],
        unique=False,
    )

    op.create_table(
        "ops_event_log",
        _id_column(),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("run_step_id", sa.BigInteger(), nullable=True),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "payload_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["ops_run.id"],
            name="fk_ops_event_log__run_id__ops_run",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_step_id"],
            ["ops_run_step.id"],
            name="fk_ops_event_log__run_step_id__ops_run_step",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ops_event_log"),
    )
    op.create_index(
        "ix_ops_event_log__run_id_created_at",
        "ops_event_log",
        ["run_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ops_event_log__run_step_id",
        "ops_event_log",
        ["run_step_id"],
        unique=False,
    )

    op.create_table(
        "ops_lock",
        _id_column(),
        sa.Column("lock_key", sa.String(length=128), nullable=False),
        sa.Column("owner_run_id", sa.BigInteger(), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "payload_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        _created_at_column(),
        _updated_at_column(),
        sa.ForeignKeyConstraint(
            ["owner_run_id"],
            ["ops_run.id"],
            name="fk_ops_lock__owner_run_id__ops_run",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ops_lock"),
        sa.UniqueConstraint("lock_key", name="uq_ops_lock__lock_key"),
    )
    op.create_index(
        "ix_ops_lock__locked_until",
        "ops_lock",
        ["locked_until"],
        unique=False,
    )
    op.create_index(
        "ix_ops_lock__owner_run_id",
        "ops_lock",
        ["owner_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ops_lock__owner_run_id", table_name="ops_lock")
    op.drop_index("ix_ops_lock__locked_until", table_name="ops_lock")
    op.drop_table("ops_lock")

    op.drop_index("ix_ops_event_log__run_step_id", table_name="ops_event_log")
    op.drop_index("ix_ops_event_log__run_id_created_at", table_name="ops_event_log")
    op.drop_table("ops_event_log")

    op.drop_index("ix_ops_run_step__run_id_sequence_no", table_name="ops_run_step")
    op.drop_index("ix_ops_run_step__run_id", table_name="ops_run_step")
    op.drop_table("ops_run_step")

    op.drop_index("ix_ops_run__requested_at", table_name="ops_run")
    op.drop_index("ix_ops_run__run_type_status", table_name="ops_run")
    op.drop_index("ix_ops_run__parent_run_id", table_name="ops_run")
    op.drop_table("ops_run")
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "m4_0001"
down_revision = "m3_0002_analytics_snapshots"
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
        "strategy_definition",
        _id_column(),
        sa.Column("strategy_code", sa.String(length=64), nullable=False),
        sa.Column("strategy_name", sa.String(length=128), nullable=False),
        sa.Column("strategy_type", sa.String(length=32), nullable=False),
        sa.Column("engine_type", sa.String(length=32), nullable=False),
        sa.Column(
            "market_scope",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'CN_A'"),
        ),
        sa.Column(
            "bar_frequency",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'1d'"),
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "lifecycle_status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column(
            "owner",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("'system'"),
        ),
        sa.Column(
            "tags_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        _created_at_column(),
        _updated_at_column(),
        sa.PrimaryKeyConstraint("id", name="pk_sd"),
        sa.UniqueConstraint("strategy_code", name="uq_sd__code"),
    )
    op.create_index(
        "ix_sd__type_status",
        "strategy_definition",
        ["strategy_type", "lifecycle_status"],
        unique=False,
    )

    op.create_table(
        "strategy_version",
        _id_column(),
        sa.Column("strategy_definition_id", sa.BigInteger(), nullable=False),
        sa.Column("version_code", sa.String(length=32), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column(
            "is_current",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "lifecycle_status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column("implementation_ref", sa.String(length=255), nullable=False),
        sa.Column(
            "dependency_spec_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "output_contract_version",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'signal_v1'"),
        ),
        sa.Column(
            "default_parameter_values_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("logic_hash", sa.String(length=64), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("retired_at", sa.Date(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        _created_at_column(),
        _updated_at_column(),
        sa.ForeignKeyConstraint(
            ["strategy_definition_id"],
            ["strategy_definition.id"],
            name="fk_sv__def_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sv"),
        sa.UniqueConstraint(
            "strategy_definition_id",
            "version_code",
            name="uq_sv__def_ver_code",
        ),
        sa.UniqueConstraint(
            "strategy_definition_id",
            "version_no",
            name="uq_sv__def_ver_no",
        ),
    )
    op.create_index(
        "ix_sv__def_current",
        "strategy_version",
        ["strategy_definition_id", "is_current"],
        unique=False,
    )
    op.create_index(
        "ix_sv__status",
        "strategy_version",
        ["lifecycle_status"],
        unique=False,
    )

    op.create_table(
        "strategy_parameter_schema",
        _id_column(),
        sa.Column("strategy_version_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "schema_version_code",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'jsonschema_v1'"),
        ),
        sa.Column(
            "parameter_schema_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "example_payload_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("validation_notes", sa.Text(), nullable=True),
        _created_at_column(),
        _updated_at_column(),
        sa.ForeignKeyConstraint(
            ["strategy_version_id"],
            ["strategy_version.id"],
            name="fk_sps__ver_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sps"),
        sa.UniqueConstraint(
            "strategy_version_id",
            name="uq_sps__ver_id",
        ),
    )
    op.create_index(
        "ix_sps__ver_id",
        "strategy_parameter_schema",
        ["strategy_version_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_sps__ver_id", table_name="strategy_parameter_schema")
    op.drop_table("strategy_parameter_schema")

    op.drop_index("ix_sv__status", table_name="strategy_version")
    op.drop_index("ix_sv__def_current", table_name="strategy_version")
    op.drop_table("strategy_version")

    op.drop_index("ix_sd__type_status", table_name="strategy_definition")
    op.drop_table("strategy_definition")
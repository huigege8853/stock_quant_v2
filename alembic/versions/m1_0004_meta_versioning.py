from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "m1_0004"
down_revision = "m1_0003"
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
        "meta_definition_version",
        _id_column(),
        sa.Column("definition_type", sa.String(length=64), nullable=False),
        sa.Column("definition_key", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("definition_hash", sa.String(length=128), nullable=False),
        sa.Column(
            "payload_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        _created_at_column(),
        _updated_at_column(),
        sa.PrimaryKeyConstraint("id", name="pk_meta_definition_version"),
        sa.UniqueConstraint(
            "definition_type",
            "definition_key",
            "version",
            name="uq_meta_definition_version__definition_type_definition_key_vers",
        ),
    )
    op.create_index(
        "ix_meta_definition_version__definition_type_definition_key",
        "meta_definition_version",
        ["definition_type", "definition_key"],
        unique=False,
    )
    op.create_index(
        "ix_meta_definition_version__status_effective_from",
        "meta_definition_version",
        ["status", "effective_from"],
        unique=False,
    )

    op.create_table(
        "meta_data_version",
        _id_column(),
        sa.Column("dataset_id", sa.BigInteger(), nullable=False),
        sa.Column("vendor_id", sa.BigInteger(), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("row_count", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        _created_at_column(),
        _updated_at_column(),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["meta_dataset.id"],
            name="fk_meta_data_version__dataset_id__meta_dataset",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["vendor_id"],
            ["meta_data_vendor.id"],
            name="fk_meta_data_version__vendor_id__meta_data_vendor",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["ops_run.id"],
            name="fk_meta_data_version__run_id__ops_run",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_meta_data_version"),
        sa.UniqueConstraint(
            "dataset_id",
            "version",
            name="uq_meta_data_version__dataset_id_version",
        ),
    )
    op.create_index(
        "ix_meta_data_version__dataset_id",
        "meta_data_version",
        ["dataset_id"],
        unique=False,
    )
    op.create_index(
        "ix_meta_data_version__vendor_id",
        "meta_data_version",
        ["vendor_id"],
        unique=False,
    )
    op.create_index(
        "ix_meta_data_version__run_id",
        "meta_data_version",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_meta_data_version__dataset_id_published_at",
        "meta_data_version",
        ["dataset_id", "published_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_meta_data_version__dataset_id_published_at", table_name="meta_data_version")
    op.drop_index("ix_meta_data_version__run_id", table_name="meta_data_version")
    op.drop_index("ix_meta_data_version__vendor_id", table_name="meta_data_version")
    op.drop_index("ix_meta_data_version__dataset_id", table_name="meta_data_version")
    op.drop_table("meta_data_version")

    op.drop_index(
        "ix_meta_definition_version__status_effective_from",
        table_name="meta_definition_version",
    )
    op.drop_index(
        "ix_meta_definition_version__definition_type_definition_key",
        table_name="meta_definition_version",
    )
    op.drop_table("meta_definition_version")
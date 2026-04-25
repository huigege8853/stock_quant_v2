from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "m1_0001"
down_revision = None
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
        "meta_market",
        _id_column(),
        sa.Column("market_code", sa.String(length=16), nullable=False),
        sa.Column("market_name", sa.String(length=64), nullable=False),
        _created_at_column(),
        _updated_at_column(),
        sa.PrimaryKeyConstraint("id", name="pk_meta_market"),
        sa.UniqueConstraint("market_code", name="uq_meta_market__market_code"),
    )

    op.create_table(
        "meta_exchange",
        _id_column(),
        sa.Column("market_id", sa.BigInteger(), nullable=False),
        sa.Column("exchange_code", sa.String(length=16), nullable=False),
        sa.Column("exchange_name", sa.String(length=64), nullable=False),
        sa.Column("timezone_name", sa.String(length=64), nullable=False),
        sa.Column("country_code", sa.String(length=8), nullable=False),
        _created_at_column(),
        _updated_at_column(),
        sa.ForeignKeyConstraint(
            ["market_id"],
            ["meta_market.id"],
            name="fk_meta_exchange__market_id__meta_market",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_meta_exchange"),
        sa.UniqueConstraint("exchange_code", name="uq_meta_exchange__exchange_code"),
    )
    op.create_index(
        "ix_meta_exchange__market_id",
        "meta_exchange",
        ["market_id"],
        unique=False,
    )

    op.create_table(
        "meta_data_vendor",
        _id_column(),
        sa.Column("vendor_code", sa.String(length=32), nullable=False),
        sa.Column("vendor_name", sa.String(length=128), nullable=False),
        sa.Column("vendor_type", sa.String(length=32), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        _created_at_column(),
        _updated_at_column(),
        sa.PrimaryKeyConstraint("id", name="pk_meta_data_vendor"),
        sa.UniqueConstraint("vendor_code", name="uq_meta_data_vendor__vendor_code"),
    )
    op.create_index(
        "ix_meta_data_vendor__vendor_type_is_active",
        "meta_data_vendor",
        ["vendor_type", "is_active"],
        unique=False,
    )

    op.create_table(
        "meta_dataset",
        _id_column(),
        sa.Column("dataset_code", sa.String(length=64), nullable=False),
        sa.Column("dataset_name", sa.String(length=128), nullable=False),
        sa.Column("layer_code", sa.String(length=32), nullable=False),
        sa.Column("grain", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        _created_at_column(),
        _updated_at_column(),
        sa.PrimaryKeyConstraint("id", name="pk_meta_dataset"),
        sa.UniqueConstraint("dataset_code", name="uq_meta_dataset__dataset_code"),
    )
    op.create_index(
        "ix_meta_dataset__layer_code_is_active",
        "meta_dataset",
        ["layer_code", "is_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_meta_dataset__layer_code_is_active", table_name="meta_dataset")
    op.drop_table("meta_dataset")

    op.drop_index("ix_meta_data_vendor__vendor_type_is_active", table_name="meta_data_vendor")
    op.drop_table("meta_data_vendor")

    op.drop_index("ix_meta_exchange__market_id", table_name="meta_exchange")
    op.drop_table("meta_exchange")

    op.drop_table("meta_market")
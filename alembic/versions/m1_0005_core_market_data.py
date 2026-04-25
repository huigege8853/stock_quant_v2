from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "m1_0005"
down_revision = "m1_0004"
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
        "core_daily_bar",
        _id_column(),
        sa.Column("instrument_id", sa.BigInteger(), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(20, 4), nullable=True),
        sa.Column("high", sa.Numeric(20, 4), nullable=True),
        sa.Column("low", sa.Numeric(20, 4), nullable=True),
        sa.Column("close", sa.Numeric(20, 4), nullable=True),
        sa.Column("pre_close", sa.Numeric(20, 4), nullable=True),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.Column("amount", sa.Numeric(20, 4), nullable=True),
        sa.Column("turnover_rate", sa.Numeric(12, 6), nullable=True),
        sa.Column(
            "is_suspended",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("data_version_id", sa.BigInteger(), nullable=False),
        _created_at_column(),
        _updated_at_column(),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["meta_instrument.id"],
            name="fk_core_daily_bar__instrument_id__meta_instrument",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["data_version_id"],
            ["meta_data_version.id"],
            name="fk_core_daily_bar__data_version_id__meta_data_version",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_core_daily_bar"),
        sa.UniqueConstraint(
            "instrument_id",
            "trade_date",
            name="uq_core_daily_bar__instrument_id_trade_date",
        ),
    )
    op.create_index(
        "ix_core_daily_bar__instrument_id",
        "core_daily_bar",
        ["instrument_id"],
        unique=False,
    )
    op.create_index(
        "ix_core_daily_bar__data_version_id",
        "core_daily_bar",
        ["data_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_core_daily_bar__trade_date",
        "core_daily_bar",
        ["trade_date"],
        unique=False,
    )

    op.create_table(
        "core_adjust_factor",
        _id_column(),
        sa.Column("instrument_id", sa.BigInteger(), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("forward_factor", sa.Numeric(20, 8), nullable=True),
        sa.Column("backward_factor", sa.Numeric(20, 8), nullable=True),
        sa.Column("data_version_id", sa.BigInteger(), nullable=False),
        _created_at_column(),
        _updated_at_column(),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["meta_instrument.id"],
            name="fk_core_adjust_factor__instrument_id__meta_instrument",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["data_version_id"],
            ["meta_data_version.id"],
            name="fk_core_adjust_factor__data_version_id__meta_data_version",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_core_adjust_factor"),
        sa.UniqueConstraint(
            "instrument_id",
            "trade_date",
            name="uq_core_adjust_factor__instrument_id_trade_date",
        ),
    )
    op.create_index(
        "ix_core_adjust_factor__instrument_id",
        "core_adjust_factor",
        ["instrument_id"],
        unique=False,
    )
    op.create_index(
        "ix_core_adjust_factor__data_version_id",
        "core_adjust_factor",
        ["data_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_core_adjust_factor__trade_date",
        "core_adjust_factor",
        ["trade_date"],
        unique=False,
    )

    op.create_table(
        "core_price_limit_daily",
        _id_column(),
        sa.Column("instrument_id", sa.BigInteger(), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("up_limit", sa.Numeric(20, 4), nullable=True),
        sa.Column("down_limit", sa.Numeric(20, 4), nullable=True),
        sa.Column("data_version_id", sa.BigInteger(), nullable=False),
        _created_at_column(),
        _updated_at_column(),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["meta_instrument.id"],
            name="fk_core_price_limit_daily__instrument_id__meta_instrument",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["data_version_id"],
            ["meta_data_version.id"],
            name="fk_core_price_limit_daily__data_version_id__meta_data_version",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_core_price_limit_daily"),
        sa.UniqueConstraint(
            "instrument_id",
            "trade_date",
            name="uq_core_price_limit_daily__instrument_id_trade_date",
        ),
    )
    op.create_index(
        "ix_core_price_limit_daily__instrument_id",
        "core_price_limit_daily",
        ["instrument_id"],
        unique=False,
    )
    op.create_index(
        "ix_core_price_limit_daily__data_version_id",
        "core_price_limit_daily",
        ["data_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_core_price_limit_daily__trade_date",
        "core_price_limit_daily",
        ["trade_date"],
        unique=False,
    )

    op.create_table(
        "core_instrument_status_daily",
        _id_column(),
        sa.Column("instrument_id", sa.BigInteger(), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("trading_status", sa.String(length=32), nullable=False),
        sa.Column(
            "is_st",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_suspended",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("data_version_id", sa.BigInteger(), nullable=False),
        _created_at_column(),
        _updated_at_column(),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["meta_instrument.id"],
            name="fk_core_instrument_status_daily__instrument_id__meta_instrument",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["data_version_id"],
            ["meta_data_version.id"],
            name="fk_core_instrument_status_daily__data_version_id__meta_data_ver",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_core_instrument_status_daily"),
        sa.UniqueConstraint(
            "instrument_id",
            "trade_date",
            name="uq_core_instrument_status_daily__instrument_id_trade_date",
        ),
    )
    op.create_index(
        "ix_core_instrument_status_daily__instrument_id",
        "core_instrument_status_daily",
        ["instrument_id"],
        unique=False,
    )
    op.create_index(
        "ix_core_instrument_status_daily__data_version_id",
        "core_instrument_status_daily",
        ["data_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_core_instrument_status_daily__trade_date",
        "core_instrument_status_daily",
        ["trade_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_core_instrument_status_daily__trade_date",
        table_name="core_instrument_status_daily",
    )
    op.drop_index(
        "ix_core_instrument_status_daily__data_version_id",
        table_name="core_instrument_status_daily",
    )
    op.drop_index(
        "ix_core_instrument_status_daily__instrument_id",
        table_name="core_instrument_status_daily",
    )
    op.drop_table("core_instrument_status_daily")

    op.drop_index(
        "ix_core_price_limit_daily__trade_date",
        table_name="core_price_limit_daily",
    )
    op.drop_index(
        "ix_core_price_limit_daily__data_version_id",
        table_name="core_price_limit_daily",
    )
    op.drop_index(
        "ix_core_price_limit_daily__instrument_id",
        table_name="core_price_limit_daily",
    )
    op.drop_table("core_price_limit_daily")

    op.drop_index(
        "ix_core_adjust_factor__trade_date",
        table_name="core_adjust_factor",
    )
    op.drop_index(
        "ix_core_adjust_factor__data_version_id",
        table_name="core_adjust_factor",
    )
    op.drop_index(
        "ix_core_adjust_factor__instrument_id",
        table_name="core_adjust_factor",
    )
    op.drop_table("core_adjust_factor")

    op.drop_index(
        "ix_core_daily_bar__trade_date",
        table_name="core_daily_bar",
    )
    op.drop_index(
        "ix_core_daily_bar__data_version_id",
        table_name="core_daily_bar",
    )
    op.drop_index(
        "ix_core_daily_bar__instrument_id",
        table_name="core_daily_bar",
    )
    op.drop_table("core_daily_bar")
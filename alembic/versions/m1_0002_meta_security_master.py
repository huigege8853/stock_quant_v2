from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "m1_0002"
down_revision = "m1_0001"
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
        "meta_instrument",
        _id_column(),
        sa.Column("market_id", sa.BigInteger(), nullable=False),
        sa.Column("exchange_id", sa.BigInteger(), nullable=False),
        sa.Column("instrument_type", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("instrument_code", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=8),
            nullable=False,
            server_default=sa.text("'CNY'"),
        ),
        sa.Column("list_date", sa.Date(), nullable=True),
        sa.Column("delist_date", sa.Date(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        _created_at_column(),
        _updated_at_column(),
        sa.ForeignKeyConstraint(
            ["market_id"],
            ["meta_market.id"],
            name="fk_meta_instrument__market_id__meta_market",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["exchange_id"],
            ["meta_exchange.id"],
            name="fk_meta_instrument__exchange_id__meta_exchange",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_meta_instrument"),
        sa.UniqueConstraint(
            "instrument_code",
            name="uq_meta_instrument__instrument_code",
        ),
        sa.UniqueConstraint(
            "exchange_id",
            "symbol",
            name="uq_meta_instrument__exchange_id_symbol",
        ),
    )
    op.create_index(
        "ix_meta_instrument__market_id",
        "meta_instrument",
        ["market_id"],
        unique=False,
    )
    op.create_index(
        "ix_meta_instrument__exchange_id",
        "meta_instrument",
        ["exchange_id"],
        unique=False,
    )
    op.create_index(
        "ix_meta_instrument__instrument_type_is_active",
        "meta_instrument",
        ["instrument_type", "is_active"],
        unique=False,
    )

    op.create_table(
        "meta_symbol_mapping",
        _id_column(),
        sa.Column("vendor_id", sa.BigInteger(), nullable=False),
        sa.Column("instrument_id", sa.BigInteger(), nullable=False),
        sa.Column("vendor_symbol", sa.String(length=64), nullable=False),
        sa.Column(
            "is_primary",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        _created_at_column(),
        _updated_at_column(),
        sa.ForeignKeyConstraint(
            ["vendor_id"],
            ["meta_data_vendor.id"],
            name="fk_meta_symbol_mapping__vendor_id__meta_data_vendor",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["meta_instrument.id"],
            name="fk_meta_symbol_mapping__instrument_id__meta_instrument",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_meta_symbol_mapping"),
        sa.UniqueConstraint(
            "vendor_id",
            "instrument_id",
            name="uq_meta_symbol_mapping__vendor_id_instrument_id",
        ),
        sa.UniqueConstraint(
            "vendor_id",
            "vendor_symbol",
            name="uq_meta_symbol_mapping__vendor_id_vendor_symbol",
        ),
    )
    op.create_index(
        "ix_meta_symbol_mapping__instrument_id",
        "meta_symbol_mapping",
        ["instrument_id"],
        unique=False,
    )
    op.create_index(
        "ix_meta_symbol_mapping__vendor_id",
        "meta_symbol_mapping",
        ["vendor_id"],
        unique=False,
    )

    op.create_table(
        "meta_trading_calendar",
        _id_column(),
        sa.Column("exchange_id", sa.BigInteger(), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column(
            "is_open",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("previous_trade_date", sa.Date(), nullable=True),
        sa.Column("next_trade_date", sa.Date(), nullable=True),
        _created_at_column(),
        _updated_at_column(),
        sa.ForeignKeyConstraint(
            ["exchange_id"],
            ["meta_exchange.id"],
            name="fk_meta_trading_calendar__exchange_id__meta_exchange",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_meta_trading_calendar"),
        sa.UniqueConstraint(
            "exchange_id",
            "trade_date",
            name="uq_meta_trading_calendar__exchange_id_trade_date",
        ),
    )
    op.create_index(
        "ix_meta_trading_calendar__trade_date",
        "meta_trading_calendar",
        ["trade_date"],
        unique=False,
    )
    op.create_index(
        "ix_meta_trading_calendar__exchange_id",
        "meta_trading_calendar",
        ["exchange_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_meta_trading_calendar__exchange_id", table_name="meta_trading_calendar")
    op.drop_index("ix_meta_trading_calendar__trade_date", table_name="meta_trading_calendar")
    op.drop_table("meta_trading_calendar")

    op.drop_index("ix_meta_symbol_mapping__vendor_id", table_name="meta_symbol_mapping")
    op.drop_index("ix_meta_symbol_mapping__instrument_id", table_name="meta_symbol_mapping")
    op.drop_table("meta_symbol_mapping")

    op.drop_index("ix_meta_instrument__instrument_type_is_active", table_name="meta_instrument")
    op.drop_index("ix_meta_instrument__exchange_id", table_name="meta_instrument")
    op.drop_index("ix_meta_instrument__market_id", table_name="meta_instrument")
    op.drop_table("meta_instrument")
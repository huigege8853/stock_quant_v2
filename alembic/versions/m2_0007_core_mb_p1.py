"""m2_0007_core_market_breadth_phase1

Revision ID: m2_0007_core_market_breadth_phase1
Revises: m2_0006_market_index_raw_staging
Create Date: 2026-04-10 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "m2_0007_core_mb_p1"
down_revision = "m2_0006_market_index_raw_staging"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "core_market_breadth",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("market_scope", sa.String(length=32), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("universe_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bar_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("advancers", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("decliners", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unchanged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("suspended_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_turnover_amount_cny", sa.Numeric(24, 6), nullable=True),
        sa.Column("mean_return", sa.Numeric(20, 8), nullable=True),
        sa.Column("median_return", sa.Numeric(20, 8), nullable=True),
        sa.Column("data_version_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=True),
        sa.ForeignKeyConstraint(
            ["data_version_id"],
            ["meta_data_version.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "market_scope",
            "trade_date",
            name="uq_core_market_breadth__market_scope_trade_date",
        ),
    )

    op.create_index(
        "ix_core_market_breadth__trade_date",
        "core_market_breadth",
        ["trade_date"],
    )
    op.create_index(
        "ix_core_market_breadth__market_scope",
        "core_market_breadth",
        ["market_scope"],
    )
    op.create_index(
        "ix_core_market_breadth__data_version_id",
        "core_market_breadth",
        ["data_version_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_core_market_breadth__data_version_id", table_name="core_market_breadth")
    op.drop_index("ix_core_market_breadth__market_scope", table_name="core_market_breadth")
    op.drop_index("ix_core_market_breadth__trade_date", table_name="core_market_breadth")
    op.drop_table("core_market_breadth")
"""m6_0002_paper_snap_ledger

Revision ID: m6_0002_paper_snap_ledger
Revises: m6_0001_trading_paper_core
Create Date: 2026-04-19
"""

from alembic import op
import sqlalchemy as sa


revision = "m6_0002_paper_snap_ledger"
down_revision = "m6_0001_trading_paper_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trading_paper_position",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("portfolio_id", sa.BigInteger(), nullable=False),
        sa.Column("instrument_id", sa.BigInteger(), nullable=False),
        sa.Column("position_date", sa.Date(), nullable=False),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("available_quantity", sa.Numeric(24, 8), nullable=False, server_default="0"),
        sa.Column("frozen_quantity", sa.Numeric(24, 8), nullable=False, server_default="0"),
        sa.Column("avg_cost", sa.Numeric(24, 8), nullable=False),
        sa.Column("cost_amount", sa.Numeric(24, 8), nullable=False),
        sa.Column("market_price", sa.Numeric(24, 8), nullable=False),
        sa.Column("market_value", sa.Numeric(24, 8), nullable=False),
        sa.Column("unrealized_pnl", sa.Numeric(24, 8), nullable=False, server_default="0"),
        sa.Column("realized_pnl", sa.Numeric(24, 8), nullable=False, server_default="0"),
        sa.Column("total_pnl", sa.Numeric(24, 8), nullable=False, server_default="0"),
        sa.Column("position_status", sa.String(length=32), nullable=False, server_default="OPEN"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["run_id"], ["ops_run.id"], name="fk_tppos_run"),
        sa.ForeignKeyConstraint(["portfolio_id"], ["trading_paper_portfolio.id"], name="fk_tppos_portfolio"),
        sa.ForeignKeyConstraint(["instrument_id"], ["meta_instrument.id"], name="fk_tppos_instrument"),
        sa.UniqueConstraint(
            "run_id",
            "portfolio_id",
            "position_date",
            "instrument_id",
            name="uq_tppos_run_portfolio_date_inst",
        ),
    )
    op.create_index("idx_tppos_portfolio_date", "trading_paper_position", ["portfolio_id", "position_date"])
    op.create_index("idx_tppos_instrument_id", "trading_paper_position", ["instrument_id"])

    op.create_table(
        "trading_paper_portfolio_snapshot",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("portfolio_id", sa.BigInteger(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("cash_balance", sa.Numeric(24, 8), nullable=False),
        sa.Column("market_value", sa.Numeric(24, 8), nullable=False),
        sa.Column("total_equity", sa.Numeric(24, 8), nullable=False),
        sa.Column("gross_exposure", sa.Numeric(24, 8), nullable=False),
        sa.Column("net_exposure", sa.Numeric(24, 8), nullable=False),
        sa.Column("holding_count", sa.Integer(), nullable=False),
        sa.Column("daily_pnl", sa.Numeric(24, 8), nullable=True),
        sa.Column("cumulative_pnl", sa.Numeric(24, 8), nullable=True),
        sa.Column("daily_return", sa.Numeric(18, 10), nullable=True),
        sa.Column("cumulative_return", sa.Numeric(18, 10), nullable=True),
        sa.Column("turnover_amount", sa.Numeric(24, 8), nullable=True),
        sa.Column("turnover_rate", sa.Numeric(18, 10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["run_id"], ["ops_run.id"], name="fk_tps_run"),
        sa.ForeignKeyConstraint(["portfolio_id"], ["trading_paper_portfolio.id"], name="fk_tps_portfolio"),
        sa.UniqueConstraint(
            "run_id",
            "portfolio_id",
            "snapshot_date",
            name="uq_tps_run_portfolio_date",
        ),
    )
    op.create_index("idx_tps_portfolio_date", "trading_paper_portfolio_snapshot", ["portfolio_id", "snapshot_date"])

    op.create_table(
        "trading_paper_trade_ledger",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("portfolio_id", sa.BigInteger(), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("instrument_id", sa.BigInteger(), nullable=True),
        sa.Column("target_position_id", sa.BigInteger(), nullable=True),
        sa.Column("order_id", sa.BigInteger(), nullable=True),
        sa.Column("fill_id", sa.BigInteger(), nullable=True),
        sa.Column("position_id", sa.BigInteger(), nullable=True),
        sa.Column("portfolio_snapshot_id", sa.BigInteger(), nullable=True),
        sa.Column("quantity_delta", sa.Numeric(24, 8), nullable=True),
        sa.Column("cash_delta", sa.Numeric(24, 8), nullable=True),
        sa.Column("amount_delta", sa.Numeric(24, 8), nullable=True),
        sa.Column("reason_code", sa.String(length=128), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["run_id"], ["ops_run.id"], name="fk_tptl_run"),
        sa.ForeignKeyConstraint(["portfolio_id"], ["trading_paper_portfolio.id"], name="fk_tptl_portfolio"),
        sa.ForeignKeyConstraint(["instrument_id"], ["meta_instrument.id"], name="fk_tptl_instrument"),
        sa.ForeignKeyConstraint(
            ["target_position_id"],
            ["trading_paper_target_position.id"],
            name="fk_tptl_target_position",
        ),
        sa.ForeignKeyConstraint(["order_id"], ["trading_paper_order.id"], name="fk_tptl_order"),
        sa.ForeignKeyConstraint(["fill_id"], ["trading_paper_fill.id"], name="fk_tptl_fill"),
        sa.ForeignKeyConstraint(["position_id"], ["trading_paper_position.id"], name="fk_tptl_position"),
        sa.ForeignKeyConstraint(
            ["portfolio_snapshot_id"],
            ["trading_paper_portfolio_snapshot.id"],
            name="fk_tptl_snapshot",
        ),
    )
    op.create_index("idx_tptl_run_id", "trading_paper_trade_ledger", ["run_id"])
    op.create_index("idx_tptl_portfolio_date", "trading_paper_trade_ledger", ["portfolio_id", "event_date"])
    op.create_index("idx_tptl_event_type", "trading_paper_trade_ledger", ["event_type"])


def downgrade() -> None:
    op.drop_index("idx_tptl_event_type", table_name="trading_paper_trade_ledger")
    op.drop_index("idx_tptl_portfolio_date", table_name="trading_paper_trade_ledger")
    op.drop_index("idx_tptl_run_id", table_name="trading_paper_trade_ledger")
    op.drop_table("trading_paper_trade_ledger")

    op.drop_index("idx_tps_portfolio_date", table_name="trading_paper_portfolio_snapshot")
    op.drop_table("trading_paper_portfolio_snapshot")

    op.drop_index("idx_tppos_instrument_id", table_name="trading_paper_position")
    op.drop_index("idx_tppos_portfolio_date", table_name="trading_paper_position")
    op.drop_table("trading_paper_position")
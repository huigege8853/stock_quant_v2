"""m6_0001_trading_paper_core

Revision ID: m6_0001_trading_paper_core
Revises: m5_0002_ops_run_result_snapshots
Create Date: 2026-04-19
"""

from alembic import op
import sqlalchemy as sa


revision = "m6_0001_trading_paper_core"
down_revision = "m5_0002_ops_run_result_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trading_paper_account",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("account_code", sa.String(length=64), nullable=False),
        sa.Column("account_name", sa.String(length=255), nullable=False),
        sa.Column("account_type", sa.String(length=32), nullable=False, server_default="PAPER"),
        sa.Column("market_code", sa.String(length=32), nullable=False, server_default="CN_A"),
        sa.Column("base_currency", sa.String(length=16), nullable=False, server_default="CNY"),
        sa.Column("initial_cash", sa.Numeric(24, 8), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("account_code", name="uq_tpa_account_code"),
    )

    op.create_table(
        "trading_paper_portfolio",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("portfolio_code", sa.String(length=64), nullable=False),
        sa.Column("portfolio_name", sa.String(length=255), nullable=False),
        sa.Column("strategy_version_id", sa.BigInteger(), nullable=False),
        sa.Column("execution_assumption_profile_id", sa.BigInteger(), nullable=False),
        sa.Column("source_signal_run_id", sa.BigInteger(), nullable=True),
        sa.Column("source_screen_request_id", sa.BigInteger(), nullable=True),
        sa.Column("portfolio_construction_mode", sa.String(length=64), nullable=False),
        sa.Column("rebalance_frequency", sa.String(length=32), nullable=False, server_default="DAILY"),
        sa.Column("max_position_count", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("long_only", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("initial_cash", sa.Numeric(24, 8), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="CREATED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["account_id"], ["trading_paper_account.id"], name="fk_tpp_account"),
        sa.ForeignKeyConstraint(["strategy_version_id"], ["strategy_version.id"], name="fk_tpp_strategy_version"),
        sa.ForeignKeyConstraint(
            ["execution_assumption_profile_id"],
            ["research_execution_assumption_profile.id"],
            name="fk_tpp_exec_profile",
        ),
        sa.ForeignKeyConstraint(["source_signal_run_id"], ["ops_run.id"], name="fk_tpp_signal_run"),
        sa.ForeignKeyConstraint(
            ["source_screen_request_id"],
            ["research_screen_request.id"],
            name="fk_tpp_screen_request",
        ),
        sa.UniqueConstraint("portfolio_code", name="uq_tpp_portfolio_code"),
    )
    op.create_index("idx_tpp_account_id", "trading_paper_portfolio", ["account_id"])
    op.create_index("idx_tpp_strategy_version_id", "trading_paper_portfolio", ["strategy_version_id"])
    op.create_index("idx_tpp_signal_run_id", "trading_paper_portfolio", ["source_signal_run_id"])

    op.create_table(
        "trading_paper_target_position",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("portfolio_id", sa.BigInteger(), nullable=False),
        sa.Column("source_signal_run_id", sa.BigInteger(), nullable=False),
        sa.Column("source_screen_request_id", sa.BigInteger(), nullable=True),
        sa.Column("strategy_signal_id", sa.BigInteger(), nullable=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("instrument_id", sa.BigInteger(), nullable=False),
        sa.Column("target_side", sa.String(length=16), nullable=False),
        sa.Column("target_weight", sa.Numeric(18, 10), nullable=False),
        sa.Column("target_amount", sa.Numeric(24, 8), nullable=True),
        sa.Column("target_quantity", sa.Numeric(24, 8), nullable=True),
        sa.Column("rank_no", sa.Integer(), nullable=True),
        sa.Column("score", sa.Numeric(18, 10), nullable=True),
        sa.Column("reason_code", sa.String(length=128), nullable=True),
        sa.Column("target_source", sa.String(length=64), nullable=False, server_default="SCREEN_RESULT"),
        sa.Column("construction_mode", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("status_reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["run_id"], ["ops_run.id"], name="fk_tpt_run"),
        sa.ForeignKeyConstraint(["portfolio_id"], ["trading_paper_portfolio.id"], name="fk_tpt_portfolio"),
        sa.ForeignKeyConstraint(["source_signal_run_id"], ["ops_run.id"], name="fk_tpt_signal_run"),
        sa.ForeignKeyConstraint(
            ["source_screen_request_id"],
            ["research_screen_request.id"],
            name="fk_tpt_screen_request",
        ),
        sa.ForeignKeyConstraint(["strategy_signal_id"], ["strategy_signal.id"], name="fk_tpt_strategy_signal"),
        sa.ForeignKeyConstraint(["instrument_id"], ["meta_instrument.id"], name="fk_tpt_instrument"),
        sa.UniqueConstraint(
            "run_id",
            "portfolio_id",
            "effective_date",
            "instrument_id",
            name="uq_tpt_run_portfolio_date_inst",
        ),
    )
    op.create_index("idx_tpt_portfolio_date", "trading_paper_target_position", ["portfolio_id", "effective_date"])
    op.create_index("idx_tpt_signal_run_id", "trading_paper_target_position", ["source_signal_run_id"])
    op.create_index("idx_tpt_screen_request_id", "trading_paper_target_position", ["source_screen_request_id"])

    op.create_table(
        "trading_paper_order",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("portfolio_id", sa.BigInteger(), nullable=False),
        sa.Column("target_position_id", sa.BigInteger(), nullable=True),
        sa.Column("instrument_id", sa.BigInteger(), nullable=False),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("order_side", sa.String(length=16), nullable=False),
        sa.Column("order_type", sa.String(length=32), nullable=False, server_default="MARKET"),
        sa.Column("price_fill_rule", sa.String(length=32), nullable=False, server_default="NEXT_OPEN"),
        sa.Column("time_in_force", sa.String(length=16), nullable=False, server_default="DAY"),
        sa.Column("target_quantity", sa.Numeric(24, 8), nullable=True),
        sa.Column("order_quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("estimated_price", sa.Numeric(24, 8), nullable=False),
        sa.Column("estimated_gross_amount", sa.Numeric(24, 8), nullable=False),
        sa.Column("estimated_fee", sa.Numeric(24, 8), nullable=False),
        sa.Column("estimated_net_amount", sa.Numeric(24, 8), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="NEW"),
        sa.Column("reject_reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["run_id"], ["ops_run.id"], name="fk_tpo_run"),
        sa.ForeignKeyConstraint(["portfolio_id"], ["trading_paper_portfolio.id"], name="fk_tpo_portfolio"),
        sa.ForeignKeyConstraint(
            ["target_position_id"],
            ["trading_paper_target_position.id"],
            name="fk_tpo_target_position",
        ),
        sa.ForeignKeyConstraint(["instrument_id"], ["meta_instrument.id"], name="fk_tpo_instrument"),
    )
    op.create_index("idx_tpo_run_id", "trading_paper_order", ["run_id"])
    op.create_index("idx_tpo_portfolio_date", "trading_paper_order", ["portfolio_id", "effective_date"])
    op.create_index("idx_tpo_target_position_id", "trading_paper_order", ["target_position_id"])

    op.create_table(
        "trading_paper_fill",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("portfolio_id", sa.BigInteger(), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("instrument_id", sa.BigInteger(), nullable=False),
        sa.Column("fill_date", sa.Date(), nullable=False),
        sa.Column("fill_price", sa.Numeric(24, 8), nullable=False),
        sa.Column("fill_quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("gross_amount", sa.Numeric(24, 8), nullable=False),
        sa.Column("commission_amount", sa.Numeric(24, 8), nullable=False, server_default="0"),
        sa.Column("stamp_duty_amount", sa.Numeric(24, 8), nullable=False, server_default="0"),
        sa.Column("transfer_fee_amount", sa.Numeric(24, 8), nullable=False, server_default="0"),
        sa.Column("slippage_amount", sa.Numeric(24, 8), nullable=False, server_default="0"),
        sa.Column("total_fee_amount", sa.Numeric(24, 8), nullable=False, server_default="0"),
        sa.Column("net_amount", sa.Numeric(24, 8), nullable=False),
        sa.Column("cash_delta", sa.Numeric(24, 8), nullable=False),
        sa.Column("price_source", sa.String(length=64), nullable=False),
        sa.Column("fill_rule", sa.String(length=32), nullable=False, server_default="NEXT_OPEN"),
        sa.Column("fill_status", sa.String(length=32), nullable=False, server_default="COMPLETED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["run_id"], ["ops_run.id"], name="fk_tpf_run"),
        sa.ForeignKeyConstraint(["portfolio_id"], ["trading_paper_portfolio.id"], name="fk_tpf_portfolio"),
        sa.ForeignKeyConstraint(["order_id"], ["trading_paper_order.id"], name="fk_tpf_order"),
        sa.ForeignKeyConstraint(["instrument_id"], ["meta_instrument.id"], name="fk_tpf_instrument"),
    )
    op.create_index("idx_tpf_run_id", "trading_paper_fill", ["run_id"])
    op.create_index("idx_tpf_portfolio_date", "trading_paper_fill", ["portfolio_id", "fill_date"])
    op.create_index("idx_tpf_order_id", "trading_paper_fill", ["order_id"])


def downgrade() -> None:
    op.drop_index("idx_tpf_order_id", table_name="trading_paper_fill")
    op.drop_index("idx_tpf_portfolio_date", table_name="trading_paper_fill")
    op.drop_index("idx_tpf_run_id", table_name="trading_paper_fill")
    op.drop_table("trading_paper_fill")

    op.drop_index("idx_tpo_target_position_id", table_name="trading_paper_order")
    op.drop_index("idx_tpo_portfolio_date", table_name="trading_paper_order")
    op.drop_index("idx_tpo_run_id", table_name="trading_paper_order")
    op.drop_table("trading_paper_order")

    op.drop_index("idx_tpt_screen_request_id", table_name="trading_paper_target_position")
    op.drop_index("idx_tpt_signal_run_id", table_name="trading_paper_target_position")
    op.drop_index("idx_tpt_portfolio_date", table_name="trading_paper_target_position")
    op.drop_table("trading_paper_target_position")

    op.drop_index("idx_tpp_signal_run_id", table_name="trading_paper_portfolio")
    op.drop_index("idx_tpp_strategy_version_id", table_name="trading_paper_portfolio")
    op.drop_index("idx_tpp_account_id", table_name="trading_paper_portfolio")
    op.drop_table("trading_paper_portfolio")

    op.drop_table("trading_paper_account")
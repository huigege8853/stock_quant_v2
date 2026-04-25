"""m5 research core

Revision ID: m5_0001_research_core
Revises: m4_0002_strategy_signal
Create Date: 2026-04-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "m5_0001_research_core"
down_revision = "m4_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_execution_assumption_profile",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("profile_code", sa.String(length=128), nullable=False),
        sa.Column("version_code", sa.String(length=64), nullable=False),
        sa.Column("profile_name", sa.String(length=255), nullable=False),
        sa.Column("market_code", sa.String(length=32), nullable=False),
        sa.Column("asset_class", sa.String(length=32), nullable=False),
        sa.Column("frequency", sa.String(length=32), nullable=False),
        sa.Column("commission_model", sa.String(length=64), nullable=True),
        sa.Column("commission_rate", sa.Numeric(20, 8), nullable=True),
        sa.Column("min_commission", sa.Numeric(20, 8), nullable=True),
        sa.Column("stamp_duty_rate", sa.Numeric(20, 8), nullable=True),
        sa.Column("transfer_fee_rate", sa.Numeric(20, 8), nullable=True),
        sa.Column("slippage_model", sa.String(length=64), nullable=True),
        sa.Column("slippage_bps", sa.Numeric(20, 8), nullable=True),
        sa.Column("price_fill_rule", sa.String(length=64), nullable=True),
        sa.Column("volume_fill_rule", sa.String(length=64), nullable=True),
        sa.Column("t_plus_rule", sa.String(length=32), nullable=True),
        sa.Column("lot_size", sa.Integer(), nullable=True),
        sa.Column(
            "allow_fractional_share",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("limit_up_down_rule", sa.String(length=64), nullable=True),
        sa.Column("suspend_rule", sa.String(length=64), nullable=True),
        sa.Column("cash_rule", sa.String(length=64), nullable=True),
        sa.Column(
            "assumption_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "profile_code",
            "version_code",
            name="uq_re_exec_profile__code_ver",
        ),
    )

    op.create_index(
        "ix_re_exec_profile__market",
        "research_execution_assumption_profile",
        ["market_code", "asset_class", "frequency"],
    )

    op.create_table(
        "research_benchmark_definition",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("benchmark_code", sa.String(length=128), nullable=False),
        sa.Column(
            "version_code",
            sa.String(length=64),
            nullable=False,
            server_default="v1",
        ),
        sa.Column("benchmark_name", sa.String(length=255), nullable=False),
        sa.Column("benchmark_type", sa.String(length=64), nullable=False),
        sa.Column("market_code", sa.String(length=32), nullable=True),
        sa.Column("market_index_id", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.String(length=16), nullable=True),
        sa.Column("rebalance_rule", sa.String(length=64), nullable=True),
        sa.Column(
            "config_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # sa.ForeignKeyConstraint(
        #     ["market_index_id"],
        #     ["core_market_index.id"],
        #     name="fk_re_benchmark__market_index",
        # ),
        sa.UniqueConstraint(
            "benchmark_code",
            "version_code",
            name="uq_re_benchmark__code_ver",
        ),
    )

    op.create_index(
        "ix_re_benchmark__type_market",
        "research_benchmark_definition",
        ["benchmark_type", "market_code"],
    )

    op.create_table(
        "research_screen_request",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("request_code", sa.String(length=128), nullable=True),
        sa.Column("request_name", sa.String(length=255), nullable=True),
        sa.Column("strategy_version_id", sa.BigInteger(), nullable=False),
        sa.Column("signal_lookup_mode", sa.String(length=32), nullable=False),
        sa.Column("source_signal_run_id", sa.BigInteger(), nullable=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("max_count", sa.Integer(), nullable=True),
        sa.Column("min_score", sa.Numeric(20, 8), nullable=True),
        sa.Column(
            "include_reason_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "exclude_reason_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "universe_filter",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "signal_filter",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "parameter_values",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "request_payload",
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["ops_run.id"],
            name="fk_re_screen_req__run",
        ),
        sa.ForeignKeyConstraint(
            ["strategy_version_id"],
            ["strategy_version.id"],
            name="fk_re_screen_req__strategy_ver",
        ),
        sa.ForeignKeyConstraint(
            ["source_signal_run_id"],
            ["ops_run.id"],
            name="fk_re_screen_req__signal_run",
        ),
        sa.UniqueConstraint("run_id", name="uq_re_screen_req__run"),
    )

    op.create_index(
        "ix_re_screen_req__strategy_date",
        "research_screen_request",
        ["strategy_version_id", "as_of_date"],
    )
    op.create_index(
        "ix_re_screen_req__signal_run",
        "research_screen_request",
        ["source_signal_run_id"],
    )
    op.create_index(
        "ix_re_screen_req__effective_date",
        "research_screen_request",
        ["effective_date"],
    )

    op.create_table(
        "research_screen_result",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("screen_request_id", sa.BigInteger(), nullable=False),
        sa.Column("signal_run_id", sa.BigInteger(), nullable=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("eligible_universe_size", sa.Integer(), nullable=True),
        sa.Column(
            "selected_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("score_min", sa.Numeric(20, 8), nullable=True),
        sa.Column("score_max", sa.Numeric(20, 8), nullable=True),
        sa.Column("score_avg", sa.Numeric(20, 8), nullable=True),
        sa.Column("result_status", sa.String(length=32), nullable=False),
        sa.Column(
            "result_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("artifact_run_id", sa.BigInteger(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["ops_run.id"],
            name="fk_re_screen_result__run",
        ),
        sa.ForeignKeyConstraint(
            ["screen_request_id"],
            ["research_screen_request.id"],
            name="fk_re_screen_result__request",
        ),
        sa.ForeignKeyConstraint(
            ["signal_run_id"],
            ["ops_run.id"],
            name="fk_re_screen_result__signal_run",
        ),
        sa.ForeignKeyConstraint(
            ["artifact_run_id"],
            ["ops_run.id"],
            name="fk_re_screen_result__artifact_run",
        ),
        sa.UniqueConstraint("run_id", name="uq_re_screen_result__run"),
    )

    op.create_index(
        "ix_re_screen_result__request",
        "research_screen_result",
        ["screen_request_id"],
    )
    op.create_index(
        "ix_re_screen_result__signal_run",
        "research_screen_result",
        ["signal_run_id"],
    )
    op.create_index(
        "ix_re_screen_result__dates",
        "research_screen_result",
        ["as_of_date", "effective_date"],
    )

    op.create_table(
        "research_backtest_request",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("request_code", sa.String(length=128), nullable=True),
        sa.Column("request_name", sa.String(length=255), nullable=True),
        sa.Column("strategy_version_id", sa.BigInteger(), nullable=False),
        sa.Column("screen_request_id", sa.BigInteger(), nullable=True),
        sa.Column("source_signal_run_id", sa.BigInteger(), nullable=True),
        sa.Column("execution_assumption_profile_id", sa.BigInteger(), nullable=False),
        sa.Column("benchmark_definition_id", sa.BigInteger(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column(
            "initial_cash",
            sa.Numeric(24, 6),
            nullable=False,
            server_default=sa.text("10000000"),
        ),
        sa.Column("rebalance_frequency", sa.String(length=32), nullable=True),
        sa.Column("signal_effective_mode", sa.String(length=64), nullable=True),
        sa.Column("portfolio_construction_mode", sa.String(length=64), nullable=True),
        sa.Column(
            "portfolio_construction_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "data_feed_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "engine_code",
            sa.String(length=64),
            nullable=False,
            server_default="backtrader",
        ),
        sa.Column(
            "engine_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "request_payload",
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["ops_run.id"],
            name="fk_re_backtest_req__run",
        ),
        sa.ForeignKeyConstraint(
            ["strategy_version_id"],
            ["strategy_version.id"],
            name="fk_re_backtest_req__strategy_ver",
        ),
        sa.ForeignKeyConstraint(
            ["screen_request_id"],
            ["research_screen_request.id"],
            name="fk_re_backtest_req__screen_req",
        ),
        sa.ForeignKeyConstraint(
            ["source_signal_run_id"],
            ["ops_run.id"],
            name="fk_re_backtest_req__signal_run",
        ),
        sa.ForeignKeyConstraint(
            ["execution_assumption_profile_id"],
            ["research_execution_assumption_profile.id"],
            name="fk_re_backtest_req__exec_profile",
        ),
        sa.ForeignKeyConstraint(
            ["benchmark_definition_id"],
            ["research_benchmark_definition.id"],
            name="fk_re_backtest_req__benchmark",
        ),
        sa.UniqueConstraint("run_id", name="uq_re_backtest_req__run"),
    )

    op.create_index(
        "ix_re_backtest_req__strategy_dates",
        "research_backtest_request",
        ["strategy_version_id", "start_date", "end_date"],
    )
    op.create_index(
        "ix_re_backtest_req__screen_req",
        "research_backtest_request",
        ["screen_request_id"],
    )
    op.create_index(
        "ix_re_backtest_req__signal_run",
        "research_backtest_request",
        ["source_signal_run_id"],
    )
    op.create_index(
        "ix_re_backtest_req__exec_profile",
        "research_backtest_request",
        ["execution_assumption_profile_id"],
    )
    op.create_index(
        "ix_re_backtest_req__benchmark",
        "research_backtest_request",
        ["benchmark_definition_id"],
    )

    op.create_table(
        "research_backtest_result",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("backtest_request_id", sa.BigInteger(), nullable=False),
        sa.Column("result_status", sa.String(length=32), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("trading_days", sa.Integer(), nullable=True),
        sa.Column("initial_cash", sa.Numeric(24, 6), nullable=True),
        sa.Column("final_equity", sa.Numeric(24, 6), nullable=True),
        sa.Column("total_return", sa.Numeric(20, 8), nullable=True),
        sa.Column("annual_return", sa.Numeric(20, 8), nullable=True),
        sa.Column("benchmark_return", sa.Numeric(20, 8), nullable=True),
        sa.Column("excess_return", sa.Numeric(20, 8), nullable=True),
        sa.Column("max_drawdown", sa.Numeric(20, 8), nullable=True),
        sa.Column("sharpe_ratio", sa.Numeric(20, 8), nullable=True),
        sa.Column("volatility", sa.Numeric(20, 8), nullable=True),
        sa.Column("win_rate", sa.Numeric(20, 8), nullable=True),
        sa.Column("turnover_avg", sa.Numeric(20, 8), nullable=True),
        sa.Column("order_count", sa.Integer(), nullable=True),
        sa.Column("trade_count", sa.Integer(), nullable=True),
        sa.Column(
            "result_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["ops_run.id"],
            name="fk_re_backtest_result__run",
        ),
        sa.ForeignKeyConstraint(
            ["backtest_request_id"],
            ["research_backtest_request.id"],
            name="fk_re_backtest_result__request",
        ),
        sa.UniqueConstraint("run_id", name="uq_re_backtest_result__run"),
    )

    op.create_index(
        "ix_re_backtest_result__request",
        "research_backtest_result",
        ["backtest_request_id"],
    )
    op.create_index(
        "ix_re_backtest_result__dates",
        "research_backtest_result",
        ["start_date", "end_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_re_backtest_result__dates", table_name="research_backtest_result")
    op.drop_index("ix_re_backtest_result__request", table_name="research_backtest_result")
    op.drop_table("research_backtest_result")

    op.drop_index("ix_re_backtest_req__benchmark", table_name="research_backtest_request")
    op.drop_index("ix_re_backtest_req__exec_profile", table_name="research_backtest_request")
    op.drop_index("ix_re_backtest_req__signal_run", table_name="research_backtest_request")
    op.drop_index("ix_re_backtest_req__screen_req", table_name="research_backtest_request")
    op.drop_index("ix_re_backtest_req__strategy_dates", table_name="research_backtest_request")
    op.drop_table("research_backtest_request")

    op.drop_index("ix_re_screen_result__dates", table_name="research_screen_result")
    op.drop_index("ix_re_screen_result__signal_run", table_name="research_screen_result")
    op.drop_index("ix_re_screen_result__request", table_name="research_screen_result")
    op.drop_table("research_screen_result")

    op.drop_index("ix_re_screen_req__effective_date", table_name="research_screen_request")
    op.drop_index("ix_re_screen_req__signal_run", table_name="research_screen_request")
    op.drop_index("ix_re_screen_req__strategy_date", table_name="research_screen_request")
    op.drop_table("research_screen_request")

    op.drop_index("ix_re_benchmark__type_market", table_name="research_benchmark_definition")
    op.drop_table("research_benchmark_definition")

    op.drop_index("ix_re_exec_profile__market", table_name="research_execution_assumption_profile")
    op.drop_table("research_execution_assumption_profile")
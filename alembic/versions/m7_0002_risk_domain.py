"""m7_0002_risk_domain

Revision ID: m7_0002_risk_domain
Revises: m7_0001_snap_ext
Create Date: 2026-04-21

M7-Risk.1:
- risk_rule
- risk_profile
- risk_profile_rule
- risk_decision

The trading domain consumes risk-adjusted target_position runs.
The original strategy_signal and original target_position runs are not mutated.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "m7_0002_risk_domain"
down_revision = "m7_0001_snap_ext"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "risk_rule",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("rule_code", sa.String(length=64), nullable=False),
        sa.Column("rule_name", sa.String(length=255), nullable=False),
        sa.Column("rule_type", sa.String(length=64), nullable=False),
        sa.Column("default_action", sa.String(length=32), nullable=False, server_default="WARN"),
        sa.Column("default_params_json", sa.JSON(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("rule_code", name="uq_risk_rule_code"),
    )
    op.create_index("idx_risk_rule_type", "risk_rule", ["rule_type"])

    op.create_table(
        "risk_profile",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("profile_code", sa.String(length=64), nullable=False),
        sa.Column("profile_name", sa.String(length=255), nullable=False),
        sa.Column("profile_type", sa.String(length=64), nullable=False, server_default="PAPER_TRADING"),
        sa.Column("market_code", sa.String(length=32), nullable=False, server_default="CN_A"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("profile_code", name="uq_risk_profile_code"),
    )
    op.create_index("idx_risk_profile_type", "risk_profile", ["profile_type"])

    op.create_table(
        "risk_profile_rule",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("profile_id", sa.BigInteger(), nullable=False),
        sa.Column("rule_id", sa.BigInteger(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("action", sa.String(length=32), nullable=False, server_default="WARN"),
        sa.Column("params_json", sa.JSON(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["profile_id"], ["risk_profile.id"], name="fk_risk_profile_rule_profile"),
        sa.ForeignKeyConstraint(["rule_id"], ["risk_rule.id"], name="fk_risk_profile_rule_rule"),
        sa.UniqueConstraint("profile_id", "rule_id", name="uq_risk_profile_rule_profile_rule"),
    )
    op.create_index("idx_risk_profile_rule_profile_priority", "risk_profile_rule", ["profile_id", "priority"])

    op.create_table(
        "risk_decision",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("portfolio_id", sa.BigInteger(), nullable=False),
        sa.Column("source_target_run_id", sa.BigInteger(), nullable=False),
        sa.Column("adjusted_target_run_id", sa.BigInteger(), nullable=False),
        sa.Column("risk_profile_id", sa.BigInteger(), nullable=False),
        sa.Column("risk_rule_id", sa.BigInteger(), nullable=True),
        sa.Column("source_target_position_id", sa.BigInteger(), nullable=True),
        sa.Column("adjusted_target_position_id", sa.BigInteger(), nullable=True),
        sa.Column("instrument_id", sa.BigInteger(), nullable=True),
        sa.Column("decision_date", sa.Date(), nullable=False),
        sa.Column("decision_type", sa.String(length=32), nullable=False),
        sa.Column("reason_code", sa.String(length=128), nullable=False),
        sa.Column("action_taken", sa.String(length=64), nullable=False),
        sa.Column("before_target_weight", sa.Numeric(18, 10), nullable=True),
        sa.Column("after_target_weight", sa.Numeric(18, 10), nullable=True),
        sa.Column("before_target_quantity", sa.Numeric(24, 8), nullable=True),
        sa.Column("after_target_quantity", sa.Numeric(24, 8), nullable=True),
        sa.Column("before_target_amount", sa.Numeric(24, 8), nullable=True),
        sa.Column("after_target_amount", sa.Numeric(24, 8), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["run_id"], ["ops_run.id"], name="fk_risk_decision_run"),
        sa.ForeignKeyConstraint(["portfolio_id"], ["trading_paper_portfolio.id"], name="fk_risk_decision_portfolio"),
        sa.ForeignKeyConstraint(["source_target_run_id"], ["ops_run.id"], name="fk_risk_decision_source_target_run"),
        sa.ForeignKeyConstraint(["adjusted_target_run_id"], ["ops_run.id"], name="fk_risk_decision_adjusted_target_run"),
        sa.ForeignKeyConstraint(["risk_profile_id"], ["risk_profile.id"], name="fk_risk_decision_profile"),
        sa.ForeignKeyConstraint(["risk_rule_id"], ["risk_rule.id"], name="fk_risk_decision_rule"),
        sa.ForeignKeyConstraint(["source_target_position_id"], ["trading_paper_target_position.id"], name="fk_risk_decision_source_target_position"),
        sa.ForeignKeyConstraint(["adjusted_target_position_id"], ["trading_paper_target_position.id"], name="fk_risk_decision_adjusted_target_position"),
        sa.ForeignKeyConstraint(["instrument_id"], ["meta_instrument.id"], name="fk_risk_decision_instrument"),
    )
    op.create_index("idx_risk_decision_run_id", "risk_decision", ["run_id"])
    op.create_index("idx_risk_decision_portfolio_date", "risk_decision", ["portfolio_id", "decision_date"])
    op.create_index("idx_risk_decision_source_target_run", "risk_decision", ["source_target_run_id"])
    op.create_index("idx_risk_decision_adjusted_target_run", "risk_decision", ["adjusted_target_run_id"])
    op.create_index("idx_risk_decision_decision_type", "risk_decision", ["decision_type"])
    op.create_index("idx_risk_decision_reason_code", "risk_decision", ["reason_code"])


def downgrade() -> None:
    op.drop_index("idx_risk_decision_reason_code", table_name="risk_decision")
    op.drop_index("idx_risk_decision_decision_type", table_name="risk_decision")
    op.drop_index("idx_risk_decision_adjusted_target_run", table_name="risk_decision")
    op.drop_index("idx_risk_decision_source_target_run", table_name="risk_decision")
    op.drop_index("idx_risk_decision_portfolio_date", table_name="risk_decision")
    op.drop_index("idx_risk_decision_run_id", table_name="risk_decision")
    op.drop_table("risk_decision")

    op.drop_index("idx_risk_profile_rule_profile_priority", table_name="risk_profile_rule")
    op.drop_table("risk_profile_rule")

    op.drop_index("idx_risk_profile_type", table_name="risk_profile")
    op.drop_table("risk_profile")

    op.drop_index("idx_risk_rule_type", table_name="risk_rule")
    op.drop_table("risk_rule")

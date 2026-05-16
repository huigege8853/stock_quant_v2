"""stage6_18d6_core_daily_bar_pct_change

Revision ID: stage6_18d6_core_daily_bar_pct_change
Revises: m7_0002_risk_domain
Create Date: 2026-05-16

Add provider-sourced daily pct_change and price_change to core_daily_bar.
The values are already present in stg_daily_bar and must be carried into core
so production reports, research reports, and scoring previews use one stable core口径.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "stage6_18d6_core_daily_bar_pct_change"
down_revision = "m7_0002_risk_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "core_daily_bar",
        sa.Column("pct_change", sa.Numeric(18, 8), nullable=True),
    )
    op.add_column(
        "core_daily_bar",
        sa.Column("price_change", sa.Numeric(18, 8), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("core_daily_bar", "price_change")
    op.drop_column("core_daily_bar", "pct_change")

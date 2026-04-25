"""m7_0001_snap_ext

Revision ID: m7_0001_snap_ext
Revises: m6_0002_paper_snap_ledger
Create Date: 2026-04-21
"""

from __future__ import annotations

from alembic import op


revision = "m7_0001_snap_ext"
down_revision = "m6_0002_paper_snap_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        alter table trading_paper_portfolio_snapshot
        add column if not exists previous_snapshot_run_id bigint;
        """
    )

    op.execute(
        """
        alter table trading_paper_portfolio_snapshot
        add column if not exists position_run_id bigint;
        """
    )

    op.execute(
        """
        alter table trading_paper_portfolio_snapshot
        add column if not exists fill_run_id bigint;
        """
    )

    op.execute(
        """
        alter table trading_paper_portfolio_snapshot
        add column if not exists previous_cash_balance numeric(28, 8) not null default 0;
        """
    )

    op.execute(
        """
        alter table trading_paper_portfolio_snapshot
        add column if not exists cash_delta numeric(28, 8) not null default 0;
        """
    )

    op.execute(
        """
        alter table trading_paper_portfolio_snapshot
        add column if not exists total_cost numeric(28, 8) not null default 0;
        """
    )

    op.execute(
        """
        alter table trading_paper_portfolio_snapshot
        add column if not exists unrealized_pnl numeric(28, 8) not null default 0;
        """
    )

    op.execute(
        """
        alter table trading_paper_portfolio_snapshot
        add column if not exists realized_pnl numeric(28, 8) not null default 0;
        """
    )

    op.execute(
        """
        alter table trading_paper_portfolio_snapshot
        add column if not exists open_position_count integer not null default 0;
        """
    )

    op.execute(
        """
        alter table trading_paper_portfolio_snapshot
        add column if not exists closed_position_count integer not null default 0;
        """
    )

    op.execute(
        """
        create index if not exists ix_tpps_position_run_id
        on trading_paper_portfolio_snapshot(position_run_id);
        """
    )

    op.execute(
        """
        create index if not exists ix_tpps_fill_run_id
        on trading_paper_portfolio_snapshot(fill_run_id);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        drop index if exists ix_tpps_fill_run_id;
        """
    )

    op.execute(
        """
        drop index if exists ix_tpps_position_run_id;
        """
    )

    op.execute(
        """
        alter table trading_paper_portfolio_snapshot
        drop column if exists closed_position_count;
        """
    )

    op.execute(
        """
        alter table trading_paper_portfolio_snapshot
        drop column if exists open_position_count;
        """
    )

    op.execute(
        """
        alter table trading_paper_portfolio_snapshot
        drop column if exists realized_pnl;
        """
    )

    op.execute(
        """
        alter table trading_paper_portfolio_snapshot
        drop column if exists unrealized_pnl;
        """
    )

    op.execute(
        """
        alter table trading_paper_portfolio_snapshot
        drop column if exists total_cost;
        """
    )

    op.execute(
        """
        alter table trading_paper_portfolio_snapshot
        drop column if exists cash_delta;
        """
    )

    op.execute(
        """
        alter table trading_paper_portfolio_snapshot
        drop column if exists previous_cash_balance;
        """
    )

    op.execute(
        """
        alter table trading_paper_portfolio_snapshot
        drop column if exists fill_run_id;
        """
    )

    op.execute(
        """
        alter table trading_paper_portfolio_snapshot
        drop column if exists position_run_id;
        """
    )

    op.execute(
        """
        alter table trading_paper_portfolio_snapshot
        drop column if exists previous_snapshot_run_id;
        """
    )
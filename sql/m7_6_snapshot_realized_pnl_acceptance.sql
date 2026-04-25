-- M7.6 snapshot realized_pnl continuity acceptance
-- Usage:
-- \set first_snapshot_run_id 149
-- \set second_snapshot_run_id 154
-- \set portfolio_id 1
-- \i sql/m7_6_snapshot_realized_pnl_acceptance.sql

select
    'snapshot_realized_pnl_chain' as section,
    prev.run_id as previous_snapshot_run_id,
    prev.snapshot_date as previous_snapshot_date,
    prev.realized_pnl as previous_realized_pnl,
    nxt.run_id as next_snapshot_run_id,
    nxt.snapshot_date as next_snapshot_date,
    nxt.realized_pnl as next_realized_pnl,
    case
        when nxt.realized_pnl = prev.realized_pnl then true
        else false
    end as realized_pnl_carry_forward_check
from trading_paper_portfolio_snapshot prev
cross join trading_paper_portfolio_snapshot nxt
where prev.run_id = :first_snapshot_run_id
  and nxt.run_id = :second_snapshot_run_id
  and prev.portfolio_id = :portfolio_id
  and nxt.portfolio_id = :portfolio_id;

select
    'snapshot_chain_summary' as section,
    run_id,
    portfolio_id,
    snapshot_date,
    previous_snapshot_run_id,
    position_run_id,
    fill_run_id,
    cash_balance,
    market_value,
    total_equity,
    realized_pnl,
    open_position_count,
    closed_position_count
from trading_paper_portfolio_snapshot
where run_id in (:first_snapshot_run_id, :second_snapshot_run_id)
  and portfolio_id = :portfolio_id
order by snapshot_date, run_id;

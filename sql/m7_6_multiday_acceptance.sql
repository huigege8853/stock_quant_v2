-- M7.6 Paper Trading Multi-Day Acceptance SQL
--
-- psql usage example:
-- \set portfolio_id 1
-- \set final_position_run_id 153
-- \set final_snapshot_run_id 154
-- \i sql/m7_6_multiday_acceptance.sql

select
    'final_position_summary' as section,
    run_id,
    portfolio_id,
    count(*) as position_count,
    count(*) filter (where coalesce(quantity, 0) > 0) as open_position_count,
    count(*) filter (where coalesce(quantity, 0) <= 0) as closed_position_count,
    coalesce(sum(quantity), 0) as quantity_total,
    coalesce(sum(available_quantity), 0) as available_quantity_total,
    coalesce(sum(realized_pnl), 0) as realized_pnl_total
from trading_paper_position
where run_id = :final_position_run_id
  and portfolio_id = :portfolio_id
group by run_id, portfolio_id;

select
    'final_position_violation' as section,
    count(*) filter (where quantity < 0) as negative_quantity_count,
    count(*) filter (where available_quantity < 0) as negative_available_quantity_count,
    count(*) filter (where available_quantity > quantity) as available_gt_quantity_count
from trading_paper_position
where run_id = :final_position_run_id
  and portfolio_id = :portfolio_id;

select
    'final_snapshot_summary' as section,
    run_id,
    portfolio_id,
    snapshot_date,
    previous_snapshot_run_id,
    position_run_id,
    fill_run_id,
    previous_cash_balance,
    cash_delta,
    cash_balance,
    market_value,
    total_equity,
    realized_pnl,
    open_position_count,
    closed_position_count,
    case when total_equity = cash_balance + market_value then true else false end as equity_check
from trading_paper_portfolio_snapshot
where run_id = :final_snapshot_run_id
  and portfolio_id = :portfolio_id;

select
    'snapshot_position_cross_check' as section,
    s.open_position_count as snapshot_open_position_count,
    p.open_position_count as actual_open_position_count,
    s.closed_position_count as snapshot_closed_position_count,
    p.closed_position_count as actual_closed_position_count,
    s.realized_pnl as snapshot_realized_pnl,
    p.realized_pnl_total as actual_realized_pnl,
    case when s.open_position_count = p.open_position_count then true else false end as open_position_count_check,
    case when s.closed_position_count = p.closed_position_count then true else false end as closed_position_count_check,
    case when s.realized_pnl = p.realized_pnl_total then true else false end as realized_pnl_check
from trading_paper_portfolio_snapshot s
cross join (
    select
        count(*) filter (where coalesce(quantity, 0) > 0) as open_position_count,
        count(*) filter (where coalesce(quantity, 0) <= 0) as closed_position_count,
        coalesce(sum(realized_pnl), 0) as realized_pnl_total
    from trading_paper_position
    where run_id = :final_position_run_id
      and portfolio_id = :portfolio_id
) p
where s.run_id = :final_snapshot_run_id
  and s.portfolio_id = :portfolio_id;

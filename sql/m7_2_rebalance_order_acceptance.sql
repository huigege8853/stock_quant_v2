-- M7.2 Paper Rebalance Order Acceptance SQL
--
-- 使用示例：
-- \set order_run_id 117
-- \set current_position_run_id 116
-- \set target_position_run_id 111
-- \set portfolio_id 1
-- \i sql/m7_2_rebalance_order_acceptance.sql

select
    'order_summary' as section,
    run_id,
    portfolio_id,
    count(*) as order_count
from trading_paper_order
where run_id = :order_run_id
  and portfolio_id = :portfolio_id
group by run_id, portfolio_id;

select
    'position_summary' as section,
    run_id,
    portfolio_id,
    count(*) as position_count,
    coalesce(sum(quantity), 0) as quantity_total,
    coalesce(sum(available_quantity), 0) as available_quantity_total
from trading_paper_position
where run_id = :current_position_run_id
  and portfolio_id = :portfolio_id
group by run_id, portfolio_id;

select
    'target_summary' as section,
    run_id,
    portfolio_id,
    count(*) as target_count
from trading_paper_target_position
where run_id = :target_position_run_id
  and portfolio_id = :portfolio_id
group by run_id, portfolio_id;
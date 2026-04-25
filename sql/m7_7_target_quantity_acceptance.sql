-- M7.7 Target Quantity Sizing Acceptance SQL
--
-- Usage:
-- \set target_position_run_id <new_target_run_id>
-- \set portfolio_id 1
-- \i sql/m7_7_target_quantity_acceptance.sql

select
    'target_quantity_summary' as section,
    run_id,
    portfolio_id,
    count(*) as target_count,
    count(*) filter (where target_quantity is not null) as target_quantity_not_null_count,
    count(*) filter (where coalesce(target_quantity, 0) > 0) as target_quantity_gt_zero_count,
    count(*) filter (where mod(target_quantity::numeric, 100) <> 0) as lot_size_violation_count,
    coalesce(sum(target_quantity), 0) as target_quantity_total,
    coalesce(sum(target_amount), 0) as target_amount_total,
    min(target_quantity) as min_target_quantity,
    max(target_quantity) as max_target_quantity
from trading_paper_target_position
where run_id = :target_position_run_id
  and portfolio_id = :portfolio_id
group by run_id, portfolio_id;

select
    'target_quantity_quality' as section,
    case when count(*) > 0 then true else false end as has_target_rows,
    case when count(*) filter (where target_quantity is null) = 0 then true else false end as target_quantity_not_null_check,
    case when count(*) filter (where coalesce(target_quantity, 0) <= 0) = 0 then true else false end as positive_target_quantity_check,
    case when count(*) filter (where mod(target_quantity::numeric, 100) <> 0) = 0 then true else false end as lot_size_100_check,
    case when coalesce(sum(target_amount), 0) > 0 then true else false end as target_amount_positive_check
from trading_paper_target_position
where run_id = :target_position_run_id
  and portfolio_id = :portfolio_id;

select
    'target_quantity_samples' as section,
    id,
    instrument_id,
    target_weight,
    target_amount,
    target_quantity,
    rank_no,
    status,
    status_reason
from trading_paper_target_position
where run_id = :target_position_run_id
  and portfolio_id = :portfolio_id
order by rank_no nulls last, instrument_id
limit 10;

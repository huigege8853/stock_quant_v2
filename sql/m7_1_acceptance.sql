-- M7.1 Paper Position Carry Forward / T+1 Acceptance SQL
--
-- psql 使用方式示例：
-- \set source_position_run_id 114
-- \set target_position_run_id 116
-- \set portfolio_id 1
-- \i sql/m7_1_acceptance.sql

select
    'source_position_summary' as section,
    run_id,
    portfolio_id,
    count(*) as position_count,
    coalesce(sum(quantity), 0) as quantity_total,
    coalesce(sum(available_quantity), 0) as available_quantity_total
from trading_paper_position
where run_id = :source_position_run_id
  and portfolio_id = :portfolio_id
group by run_id, portfolio_id;

select
    'target_position_summary' as section,
    run_id,
    portfolio_id,
    count(*) as position_count,
    coalesce(sum(quantity), 0) as quantity_total,
    coalesce(sum(available_quantity), 0) as available_quantity_total
from trading_paper_position
where run_id = :target_position_run_id
  and portfolio_id = :portfolio_id
group by run_id, portfolio_id;

select
    'm7_1_quality' as section,
    src.position_count as source_position_count,
    tgt.position_count as target_position_count,
    src.quantity_total as source_quantity_total,
    tgt.quantity_total as target_quantity_total,
    tgt.available_quantity_total as target_available_quantity_total,
    case when src.position_count = tgt.position_count then true else false end as position_count_check,
    case when src.quantity_total = tgt.quantity_total then true else false end as quantity_total_check,
    case when tgt.available_quantity_total = tgt.quantity_total then true else false end as t_plus_1_available_quantity_check
from (
    select
        count(*) as position_count,
        coalesce(sum(quantity), 0) as quantity_total
    from trading_paper_position
    where run_id = :source_position_run_id
      and portfolio_id = :portfolio_id
) src
cross join (
    select
        count(*) as position_count,
        coalesce(sum(quantity), 0) as quantity_total,
        coalesce(sum(available_quantity), 0) as available_quantity_total
    from trading_paper_position
    where run_id = :target_position_run_id
      and portfolio_id = :portfolio_id
) tgt;

select
    'target_position_violation' as section,
    count(*) filter (where quantity < 0) as negative_quantity_count,
    count(*) filter (where available_quantity < 0) as negative_available_quantity_count,
    count(*) filter (where available_quantity > quantity) as available_gt_quantity_count
from trading_paper_position
where run_id = :target_position_run_id
  and portfolio_id = :portfolio_id;
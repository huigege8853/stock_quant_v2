-- M7-Risk.1 Acceptance SQL
--
-- Usage:
-- \set source_target_run_id 155
-- \set adjusted_target_run_id 156
-- \set portfolio_id 1
-- \i sql/m7_risk_1_acceptance.sql

select
    'source_target_summary' as section,
    run_id,
    portfolio_id,
    count(*) as target_count,
    coalesce(sum(target_quantity), 0) as target_quantity_total,
    coalesce(sum(target_amount), 0) as target_amount_total
from trading_paper_target_position
where run_id = :source_target_run_id
  and portfolio_id = :portfolio_id
group by run_id, portfolio_id;

select
    'adjusted_target_summary' as section,
    run_id,
    portfolio_id,
    count(*) as target_count,
    coalesce(sum(target_quantity), 0) as target_quantity_total,
    coalesce(sum(target_amount), 0) as target_amount_total,
    count(*) filter (where status = 'REJECTED') as rejected_target_count,
    count(*) filter (where status = 'RISK_ADJUSTED') as adjusted_target_count,
    count(*) filter (where status = 'RISK_PASSED') as passed_target_count
from trading_paper_target_position
where run_id = :adjusted_target_run_id
  and portfolio_id = :portfolio_id
group by run_id, portfolio_id;

select
    'risk_decision_summary' as section,
    source_target_run_id,
    adjusted_target_run_id,
    portfolio_id,
    count(*) as decision_count,
    count(*) filter (where decision_type = 'PASS') as pass_count,
    count(*) filter (where decision_type = 'WARN') as warn_count,
    count(*) filter (where decision_type = 'REJECT') as reject_count,
    count(*) filter (where decision_type = 'ADJUST') as adjust_count
from risk_decision
where source_target_run_id = :source_target_run_id
  and adjusted_target_run_id = :adjusted_target_run_id
  and portfolio_id = :portfolio_id
group by source_target_run_id, adjusted_target_run_id, portfolio_id;

select
    'risk_reason_summary' as section,
    decision_type,
    reason_code,
    count(*) as decision_count
from risk_decision
where source_target_run_id = :source_target_run_id
  and adjusted_target_run_id = :adjusted_target_run_id
  and portfolio_id = :portfolio_id
group by decision_type, reason_code
order by decision_type, reason_code;

select
    'm7_risk_quality' as section,
    case when src.target_count > 0 then true else false end as source_target_exists,
    case when adj.target_count > 0 then true else false end as adjusted_target_exists,
    case when src.target_count = adj.target_count then true else false end as same_target_row_count,
    case when dec.decision_count > 0 then true else false end as decision_exists,
    case when dec.warn_count + dec.reject_count + dec.adjust_count > 0 then true else false end as has_risk_effect
from (
    select count(*) as target_count
    from trading_paper_target_position
    where run_id = :source_target_run_id
      and portfolio_id = :portfolio_id
) src
cross join (
    select count(*) as target_count
    from trading_paper_target_position
    where run_id = :adjusted_target_run_id
      and portfolio_id = :portfolio_id
) adj
cross join (
    select
        count(*) as decision_count,
        count(*) filter (where decision_type = 'WARN') as warn_count,
        count(*) filter (where decision_type = 'REJECT') as reject_count,
        count(*) filter (where decision_type = 'ADJUST') as adjust_count
    from risk_decision
    where source_target_run_id = :source_target_run_id
      and adjusted_target_run_id = :adjusted_target_run_id
      and portfolio_id = :portfolio_id
) dec;

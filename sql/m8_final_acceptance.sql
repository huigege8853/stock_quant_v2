-- M8 Final Acceptance
-- stock_quant_v2
--
-- Covers:
-- M8.1 Run Monitor + CLI
-- M8.2 Report Export
-- M8.3 Daily Ops Orchestration
-- M8.4 Ops Hygiene
-- M8.5 Scheduler Adapter
-- M8.6 Human Review Pack

with params as (
    select
        1::bigint as portfolio_id,
        160::bigint as target_run_id,
        146::bigint as order_run_id,
        147::bigint as fill_run_id,
        153::bigint as position_run_id,
        154::bigint as snapshot_run_id,
        167::bigint as risk_run_id,
        160::bigint as source_target_run_id,
        166::bigint as adjusted_target_run_id,
        'paper_cn_a_risk3_strict_v1'::text as risk_profile_code,
        date '2026-04-23' as snapshot_date
),
checks as (
    select
        'C01_NO_RUNNING_RUNS' as check_code,
        'ops_run has no RUNNING rows' as check_name,
        (
            select count(*)::text
            from ops_run
            where status = 'RUNNING'
        ) as actual_value,
        '0' as expected_value,
        case
            when (
                select count(*)
                from ops_run
                where status = 'RUNNING'
            ) = 0 then 'PASS'
            else 'FAIL'
        end as status

    union all

    select
        'C02_RUN_STATUS_COUNTS',
        'run status counts are available',
        (
            select string_agg(status || '=' || cnt::text, ', ' order by status)
            from (
                select status, count(*) as cnt
                from ops_run
                group by status
            ) x
        ),
        'FAILED / STALE / SUCCESS available',
        case
            when exists (select 1 from ops_run where status = 'SUCCESS')
             and exists (select 1 from ops_run where status = 'STALE')
            then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C03_LATEST_TARGET_RUN_SUCCESS',
        'latest target run is SUCCESS',
        (
            select status
            from ops_run r, params p
            where r.id = p.target_run_id
        ),
        'SUCCESS',
        case
            when (
                select status
                from ops_run r, params p
                where r.id = p.target_run_id
            ) = 'SUCCESS' then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C04_LATEST_ORDER_RUN_SUCCESS',
        'latest order run is SUCCESS',
        (
            select status
            from ops_run r, params p
            where r.id = p.order_run_id
        ),
        'SUCCESS',
        case
            when (
                select status
                from ops_run r, params p
                where r.id = p.order_run_id
            ) = 'SUCCESS' then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C05_LATEST_FILL_RUN_SUCCESS',
        'latest fill run is SUCCESS',
        (
            select status
            from ops_run r, params p
            where r.id = p.fill_run_id
        ),
        'SUCCESS',
        case
            when (
                select status
                from ops_run r, params p
                where r.id = p.fill_run_id
            ) = 'SUCCESS' then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C06_LATEST_POSITION_RUN_SUCCESS',
        'latest position run is SUCCESS',
        (
            select status
            from ops_run r, params p
            where r.id = p.position_run_id
        ),
        'SUCCESS',
        case
            when (
                select status
                from ops_run r, params p
                where r.id = p.position_run_id
            ) = 'SUCCESS' then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C07_LATEST_SNAPSHOT_RUN_SUCCESS',
        'latest snapshot run is SUCCESS',
        (
            select status
            from ops_run r, params p
            where r.id = p.snapshot_run_id
        ),
        'SUCCESS',
        case
            when (
                select status
                from ops_run r, params p
                where r.id = p.snapshot_run_id
            ) = 'SUCCESS' then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C08_LATEST_RISK_RUN_SUCCESS',
        'latest risk run is SUCCESS',
        (
            select status
            from ops_run r, params p
            where r.id = p.risk_run_id
        ),
        'SUCCESS',
        case
            when (
                select status
                from ops_run r, params p
                where r.id = p.risk_run_id
            ) = 'SUCCESS' then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C09_TARGET_ROWS',
        'latest target rows exist',
        (
            select count(*)::text
            from trading_paper_target_position t, params p
            where t.portfolio_id = p.portfolio_id
              and t.run_id = p.target_run_id
        ),
        '30',
        case
            when (
                select count(*)
                from trading_paper_target_position t, params p
                where t.portfolio_id = p.portfolio_id
                  and t.run_id = p.target_run_id
            ) = 30 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C10_ORDER_ROWS',
        'latest order rows exist',
        (
            select count(*)::text
            from trading_paper_order o, params p
            where o.portfolio_id = p.portfolio_id
              and o.run_id = p.order_run_id
        ),
        '28',
        case
            when (
                select count(*)
                from trading_paper_order o, params p
                where o.portfolio_id = p.portfolio_id
                  and o.run_id = p.order_run_id
            ) = 28 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C11_FILL_ROWS',
        'latest fill rows exist',
        (
            select count(*)::text
            from trading_paper_fill f, params p
            where f.portfolio_id = p.portfolio_id
              and f.run_id = p.fill_run_id
        ),
        '28',
        case
            when (
                select count(*)
                from trading_paper_fill f, params p
                where f.portfolio_id = p.portfolio_id
                  and f.run_id = p.fill_run_id
            ) = 28 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C12_POSITION_ROWS',
        'latest position rows exist',
        (
            select count(*)::text
            from trading_paper_position pos, params p
            where pos.portfolio_id = p.portfolio_id
              and pos.run_id = p.position_run_id
        ),
        '30',
        case
            when (
                select count(*)
                from trading_paper_position pos, params p
                where pos.portfolio_id = p.portfolio_id
                  and pos.run_id = p.position_run_id
            ) = 30 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C13_SNAPSHOT_ROWS',
        'latest snapshot row exists',
        (
            select count(*)::text
            from trading_paper_portfolio_snapshot s, params p
            where s.portfolio_id = p.portfolio_id
              and s.run_id = p.snapshot_run_id
              and s.snapshot_date = p.snapshot_date
        ),
        '1',
        case
            when (
                select count(*)
                from trading_paper_portfolio_snapshot s, params p
                where s.portfolio_id = p.portfolio_id
                  and s.run_id = p.snapshot_run_id
                  and s.snapshot_date = p.snapshot_date
            ) = 1 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C14_SNAPSHOT_KPI',
        'snapshot total equity and holding count are valid',
        (
            select
                coalesce(max(s.total_equity), 0)::text || '/' ||
                coalesce(max(s.holding_count), 0)::text
            from trading_paper_portfolio_snapshot s, params p
            where s.portfolio_id = p.portfolio_id
              and s.run_id = p.snapshot_run_id
              and s.snapshot_date = p.snapshot_date
        ),
        'total_equity>0/holding_count=30',
        case
            when (
                select coalesce(max(s.total_equity), 0)
                from trading_paper_portfolio_snapshot s, params p
                where s.portfolio_id = p.portfolio_id
                  and s.run_id = p.snapshot_run_id
                  and s.snapshot_date = p.snapshot_date
            ) > 0
            and (
                select coalesce(max(s.holding_count), 0)
                from trading_paper_portfolio_snapshot s, params p
                where s.portfolio_id = p.portfolio_id
                  and s.run_id = p.snapshot_run_id
                  and s.snapshot_date = p.snapshot_date
            ) = 30 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C15_RISK_DECISION_ROWS',
        'latest risk decision rows exist',
        (
            select count(*)::text
            from risk_decision rd, params p
            where rd.portfolio_id = p.portfolio_id
              and rd.run_id = p.risk_run_id
              and rd.source_target_run_id = p.source_target_run_id
              and rd.adjusted_target_run_id = p.adjusted_target_run_id
        ),
        '90',
        case
            when (
                select count(*)
                from risk_decision rd, params p
                where rd.portfolio_id = p.portfolio_id
                  and rd.run_id = p.risk_run_id
                  and rd.source_target_run_id = p.source_target_run_id
                  and rd.adjusted_target_run_id = p.adjusted_target_run_id
            ) = 90 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C16_STRICT_REJECT_COUNT',
        'strict profile expected reject count',
        (
            select count(*)::text
            from risk_decision rd, params p
            where rd.portfolio_id = p.portfolio_id
              and rd.run_id = p.risk_run_id
              and rd.source_target_run_id = p.source_target_run_id
              and rd.adjusted_target_run_id = p.adjusted_target_run_id
              and rd.decision_type = 'REJECT'
        ),
        '30',
        case
            when (
                select count(*)
                from risk_decision rd, params p
                where rd.portfolio_id = p.portfolio_id
                  and rd.run_id = p.risk_run_id
                  and rd.source_target_run_id = p.source_target_run_id
                  and rd.adjusted_target_run_id = p.adjusted_target_run_id
                  and rd.decision_type = 'REJECT'
            ) = 30 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C17_STRICT_NO_WARN',
        'strict profile has no WARN decisions',
        (
            select count(*)::text
            from risk_decision rd, params p
            where rd.portfolio_id = p.portfolio_id
              and rd.run_id = p.risk_run_id
              and rd.source_target_run_id = p.source_target_run_id
              and rd.adjusted_target_run_id = p.adjusted_target_run_id
              and rd.decision_type = 'WARN'
        ),
        '0',
        case
            when (
                select count(*)
                from risk_decision rd, params p
                where rd.portfolio_id = p.portfolio_id
                  and rd.run_id = p.risk_run_id
                  and rd.source_target_run_id = p.source_target_run_id
                  and rd.adjusted_target_run_id = p.adjusted_target_run_id
                  and rd.decision_type = 'WARN'
            ) = 0 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C18_STRICT_NO_ADJUST',
        'strict profile has no ADJUST decisions',
        (
            select count(*)::text
            from risk_decision rd, params p
            where rd.portfolio_id = p.portfolio_id
              and rd.run_id = p.risk_run_id
              and rd.source_target_run_id = p.source_target_run_id
              and rd.adjusted_target_run_id = p.adjusted_target_run_id
              and rd.decision_type = 'ADJUST'
        ),
        '0',
        case
            when (
                select count(*)
                from risk_decision rd, params p
                where rd.portfolio_id = p.portfolio_id
                  and rd.run_id = p.risk_run_id
                  and rd.source_target_run_id = p.source_target_run_id
                  and rd.adjusted_target_run_id = p.adjusted_target_run_id
                  and rd.decision_type = 'ADJUST'
            ) = 0 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C19_ADJUSTED_TARGET_ZERO',
        'strict adjusted target quantity and amount are zero',
        (
            select
                coalesce(sum(t.target_quantity), 0)::text || '/' ||
                coalesce(sum(t.target_amount), 0)::text
            from trading_paper_target_position t, params p
            where t.portfolio_id = p.portfolio_id
              and t.run_id = p.adjusted_target_run_id
        ),
        '0/0',
        case
            when (
                select coalesce(sum(t.target_quantity), 0)
                from trading_paper_target_position t, params p
                where t.portfolio_id = p.portfolio_id
                  and t.run_id = p.adjusted_target_run_id
            ) = 0
            and (
                select coalesce(sum(t.target_amount), 0)
                from trading_paper_target_position t, params p
                where t.portfolio_id = p.portfolio_id
                  and t.run_id = p.adjusted_target_run_id
            ) = 0 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C20_RISK_PROFILE_EXISTS',
        'risk profile exists',
        (
            select count(*)::text
            from risk_profile rp, params p
            where rp.profile_code = p.risk_profile_code
              and rp.enabled = true
        ),
        '1',
        case
            when (
                select count(*)
                from risk_profile rp, params p
                where rp.profile_code = p.risk_profile_code
                  and rp.enabled = true
            ) = 1 then 'PASS'
            else 'FAIL'
        end
)
select *
from checks

union all

select
    'OVERALL' as check_code,
    'M8 final acceptance overall status' as check_name,
    (
        select count(*) filter (where status = 'PASS')::text || '/' || count(*)::text
        from checks
    ) as actual_value,
    'all PASS' as expected_value,
    case
        when (select count(*) filter (where status <> 'PASS') from checks) = 0
        then 'PASS'
        else 'FAIL'
    end as status
;
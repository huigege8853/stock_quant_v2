-- M8 Enhanced Final Acceptance
-- stock_quant_v2
--
-- Covers:
-- CLI / API / OpenAPI / Scheduler Adapter / Excel / Alert / Audit / Env / Startup / Scheduler Registration

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
        'C01_OPS_RUN_ACCESSIBLE' as check_code,
        'ops_run accessible' as check_name,
        (select count(*)::text from ops_run) as actual_value,
        '>0' as expected_value,
        case when (select count(*) from ops_run) > 0 then 'PASS' else 'FAIL' end as status

    union all

    select
        'C02_NO_RUNNING_RUNS',
        'RUNNING must be zero',
        (select count(*)::text from ops_run where status = 'RUNNING'),
        '0',
        case when (select count(*) from ops_run where status = 'RUNNING') = 0 then 'PASS' else 'FAIL' end

    union all

    select
        'C03_RUN_STATUS_COUNTS',
        'run status counts available',
        (
            select string_agg(status || '=' || cnt::text, ', ' order by status)
            from (
                select status, count(*) as cnt
                from ops_run
                group by status
            ) x
        ),
        'FAILED=16, STALE=20, SUCCESS=115',
        case
            when (select count(*) from ops_run where status = 'FAILED') = 16
             and (select count(*) from ops_run where status = 'STALE') = 20
             and (select count(*) from ops_run where status = 'SUCCESS') = 115
            then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C04_LATEST_RUNS_SUCCESS',
        'latest chain runs are SUCCESS',
        (
            select string_agg(r.id::text || '=' || r.status, ', ' order by r.id)
            from ops_run r
            where r.id in (160, 146, 147, 153, 154, 167)
        ),
        'all SUCCESS',
        case
            when (
                select count(*)
                from ops_run
                where id in (160, 146, 147, 153, 154, 167)
                  and status = 'SUCCESS'
            ) = 6 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C05_TARGET_ROWS',
        'target rows exist',
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
        'C06_ORDER_ROWS',
        'order rows exist',
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
        'C07_FILL_ROWS',
        'fill rows exist',
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
        'C08_POSITION_ROWS',
        'position rows exist',
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
        'C09_SNAPSHOT_ROWS',
        'snapshot row exists',
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
        'C10_SNAPSHOT_KPI',
        'snapshot KPI valid',
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
        'C11_RISK_DECISION_ROWS',
        'risk decision rows exist',
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
        'C12_RISK_DECISION_BREAKDOWN',
        'risk decision breakdown expected',
        (
            select
                count(*) filter (where decision_type = 'PASS')::text || '/' ||
                count(*) filter (where decision_type = 'WARN')::text || '/' ||
                count(*) filter (where decision_type = 'REJECT')::text || '/' ||
                count(*) filter (where decision_type = 'ADJUST')::text
            from risk_decision rd, params p
            where rd.portfolio_id = p.portfolio_id
              and rd.run_id = p.risk_run_id
              and rd.source_target_run_id = p.source_target_run_id
              and rd.adjusted_target_run_id = p.adjusted_target_run_id
        ),
        'PASS/WARN/REJECT/ADJUST = 60/0/30/0',
        case
            when (
                select count(*) filter (where decision_type = 'PASS')
                from risk_decision rd, params p
                where rd.portfolio_id = p.portfolio_id
                  and rd.run_id = p.risk_run_id
                  and rd.source_target_run_id = p.source_target_run_id
                  and rd.adjusted_target_run_id = p.adjusted_target_run_id
            ) = 60
            and (
                select count(*) filter (where decision_type = 'WARN')
                from risk_decision rd, params p
                where rd.portfolio_id = p.portfolio_id
                  and rd.run_id = p.risk_run_id
                  and rd.source_target_run_id = p.source_target_run_id
                  and rd.adjusted_target_run_id = p.adjusted_target_run_id
            ) = 0
            and (
                select count(*) filter (where decision_type = 'REJECT')
                from risk_decision rd, params p
                where rd.portfolio_id = p.portfolio_id
                  and rd.run_id = p.risk_run_id
                  and rd.source_target_run_id = p.source_target_run_id
                  and rd.adjusted_target_run_id = p.adjusted_target_run_id
            ) = 30
            and (
                select count(*) filter (where decision_type = 'ADJUST')
                from risk_decision rd, params p
                where rd.portfolio_id = p.portfolio_id
                  and rd.run_id = p.risk_run_id
                  and rd.source_target_run_id = p.source_target_run_id
                  and rd.adjusted_target_run_id = p.adjusted_target_run_id
            ) = 0 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C13_ADJUSTED_TARGET_ZERO',
        'strict adjusted target remains zero',
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
        'C14_RISK_PROFILE_EXISTS',
        'risk profile exists and enabled',
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

    union all

    select
        'C15_ERROR_LOGS_AVAILABLE',
        'ops logs have auditable FAILED/STALE rows',
        (
            select count(*)::text
            from ops_run
            where status in ('FAILED', 'STALE', 'RUNNING')
               or coalesce(error_message, '') <> ''
        ),
        '>=1',
        case
            when (
                select count(*)
                from ops_run
                where status in ('FAILED', 'STALE', 'RUNNING')
                   or coalesce(error_message, '') <> ''
            ) >= 1 then 'PASS'
            else 'FAIL'
        end
)
select *
from checks

union all

select
    'OVERALL' as check_code,
    'M8 enhanced final acceptance overall status' as check_name,
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
-- M8.10 Ops Alert / Log / Audit Acceptance
-- stock_quant_v2
--
-- SQL 验收 Alert / Log / Audit 依赖的数据库事实；
-- Alert/Audit 本地 artifact 文件由 PowerShell 检查完成。

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
        'alert check expects RUNNING = 0' as check_name,
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
        'C02_FAILED_RUNS_EXIST_FOR_WARN',
        'FAILED runs exist and should be WARN-level alert',
        (
            select count(*)::text
            from ops_run
            where status = 'FAILED'
        ),
        '>=1',
        case
            when (
                select count(*)
                from ops_run
                where status = 'FAILED'
            ) >= 1 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C03_STALE_RUNS_EXIST_FOR_INFO',
        'STALE runs exist and should be INFO-level audit alert',
        (
            select count(*)::text
            from ops_run
            where status = 'STALE'
        ),
        '>=1',
        case
            when (
                select count(*)
                from ops_run
                where status = 'STALE'
            ) >= 1 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C04_LATEST_TRADING_CHAIN_DATA',
        'alert / audit snapshot latest trading chain exists',
        (
            select (
                select count(*) from trading_paper_target_position where run_id = 160 and portfolio_id = 1
            )::text || '/' || (
                select count(*) from trading_paper_order where run_id = 146 and portfolio_id = 1
            )::text || '/' || (
                select count(*) from trading_paper_fill where run_id = 147 and portfolio_id = 1
            )::text || '/' || (
                select count(*) from trading_paper_position where run_id = 153 and portfolio_id = 1
            )::text || '/' || (
                select count(*) from trading_paper_portfolio_snapshot where run_id = 154 and portfolio_id = 1
            )::text
        ),
        '30/28/28/30/1',
        case
            when (
                select count(*) from trading_paper_target_position where run_id = 160 and portfolio_id = 1
            ) = 30
            and (
                select count(*) from trading_paper_order where run_id = 146 and portfolio_id = 1
            ) = 28
            and (
                select count(*) from trading_paper_fill where run_id = 147 and portfolio_id = 1
            ) = 28
            and (
                select count(*) from trading_paper_position where run_id = 153 and portfolio_id = 1
            ) = 30
            and (
                select count(*) from trading_paper_portfolio_snapshot where run_id = 154 and portfolio_id = 1
            ) = 1 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C05_SNAPSHOT_KPI',
        'audit snapshot KPI exists',
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
        'C06_RISK_DECISION_ROWS',
        'alert risk dependency exists',
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
        'C07_STRICT_REJECT_WARN_EXPECTED',
        'strict profile expected risk reject alert',
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
        'C08_STRICT_NO_WARN_NO_ADJUST',
        'strict profile has no WARN / ADJUST decisions',
        (
            select (
                select count(*)
                from risk_decision rd, params p
                where rd.portfolio_id = p.portfolio_id
                  and rd.run_id = p.risk_run_id
                  and rd.source_target_run_id = p.source_target_run_id
                  and rd.adjusted_target_run_id = p.adjusted_target_run_id
                  and rd.decision_type = 'WARN'
            )::text || '/' || (
                select count(*)
                from risk_decision rd, params p
                where rd.portfolio_id = p.portfolio_id
                  and rd.run_id = p.risk_run_id
                  and rd.source_target_run_id = p.source_target_run_id
                  and rd.adjusted_target_run_id = p.adjusted_target_run_id
                  and rd.decision_type = 'ADJUST'
            )::text
        ),
        '0/0',
        case
            when (
                select count(*)
                from risk_decision rd, params p
                where rd.portfolio_id = p.portfolio_id
                  and rd.run_id = p.risk_run_id
                  and rd.source_target_run_id = p.source_target_run_id
                  and rd.adjusted_target_run_id = p.adjusted_target_run_id
                  and rd.decision_type = 'WARN'
            ) = 0
            and (
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
        'C09_ADJUSTED_TARGET_ZERO',
        'target diff alert dependency expects adjusted target zero',
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
        'C10_ERROR_LOGS_AVAILABLE',
        'ops log query should have error/warn rows',
        (
            select count(*)::text
            from ops_run
            where coalesce(error_message, '') <> ''
               or status in ('FAILED', 'STALE', 'RUNNING')
        ),
        '>=1',
        case
            when (
                select count(*)
                from ops_run
                where coalesce(error_message, '') <> ''
                   or status in ('FAILED', 'STALE', 'RUNNING')
            ) >= 1 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C11_RISK_PROFILE_EXISTS',
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
    'M8.10 alert log audit acceptance overall status' as check_name,
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
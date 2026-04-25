-- M8.12 Scheduler Registration Manual Acceptance
-- stock_quant_v2
--
-- SQL 验收 Scheduler Registration 依赖的数据事实；
-- PS1/XML/README/registration pack 文件由 CLI 和 PowerShell artifact check 验收。

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
        'scheduler registration expects RUNNING = 0' as check_name,
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
        'C02_LATEST_RUNS_SUCCESS',
        'latest trading/risk run statuses are SUCCESS',
        (
            select string_agg(r.id::text || '=' || r.status, ', ' order by r.id)
            from ops_run r
            where r.id in (160, 146, 147, 153, 154, 167)
        ),
        'all SUCCESS',
        case
            when (
                select count(*)
                from ops_run r
                where r.id in (160, 146, 147, 153, 154, 167)
                  and r.status = 'SUCCESS'
            ) = 6 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C03_LATEST_TRADING_CHAIN_DATA',
        'latest trading chain data exists',
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
        'C04_SNAPSHOT_KPI',
        'latest snapshot KPI is valid',
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
        'C05_RISK_DECISION_ROWS',
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
        'C06_STRICT_REJECT_EXPECTED',
        'strict profile expected REJECT count',
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
        'C07_STRICT_NO_WARN_NO_ADJUST',
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
        'C08_ADJUSTED_TARGET_ZERO',
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
        'C09_RISK_PROFILE_EXISTS',
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
    'M8.12 scheduler registration acceptance overall status' as check_name,
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
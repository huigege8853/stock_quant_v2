-- M8.6 Ops Dashboard / Human Review Pack Acceptance
-- stock_quant_v2
--
-- SQL 只验收 Human Review Pack 依赖的数据库事实；
-- 本地 artifacts 文件由 PowerShell 文件检查完成。

with checks as (
    select
        'C01_NO_RUNNING_RUNS' as check_code,
        'ops_run should have no RUNNING rows' as check_name,
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
        'C02_STALE_COUNT',
        'STALE count should be at least 20',
        (
            select count(*)::text
            from ops_run
            where status = 'STALE'
        ),
        '>=20',
        case
            when (
                select count(*)
                from ops_run
                where status = 'STALE'
            ) >= 20 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C03_SUCCESS_COUNT',
        'SUCCESS count should be at least 115',
        (
            select count(*)::text
            from ops_run
            where status = 'SUCCESS'
        ),
        '>=115',
        case
            when (
                select count(*)
                from ops_run
                where status = 'SUCCESS'
            ) >= 115 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C04_FAILED_COUNT',
        'FAILED count should be available',
        (
            select count(*)::text
            from ops_run
            where status = 'FAILED'
        ),
        '>=0',
        case
            when (
                select count(*)
                from ops_run
                where status = 'FAILED'
            ) >= 0 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C05_LATEST_TRADING_CHAIN_DATA',
        'latest trading chain data exists',
        (
            select (
                select count(*) from trading_paper_order where run_id = 146
            )::text || '/' || (
                select count(*) from trading_paper_fill where run_id = 147
            )::text || '/' || (
                select count(*) from trading_paper_position where run_id = 153
            )::text || '/' || (
                select count(*) from trading_paper_portfolio_snapshot where run_id = 154
            )::text
        ),
        '28/28/30/1',
        case
            when (
                select count(*) from trading_paper_order where run_id = 146
            ) = 28
            and (
                select count(*) from trading_paper_fill where run_id = 147
            ) = 28
            and (
                select count(*) from trading_paper_position where run_id = 153
            ) = 30
            and (
                select count(*) from trading_paper_portfolio_snapshot where run_id = 154
            ) = 1
            then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C06_LATEST_SNAPSHOT_KPI',
        'latest snapshot KPI should exist',
        (
            select
                coalesce(max(total_equity), 0)::text || '/' ||
                coalesce(max(holding_count), 0)::text
            from trading_paper_portfolio_snapshot
            where portfolio_id = 1
              and run_id = 154
              and snapshot_date = date '2026-04-23'
        ),
        'total_equity>0/holding_count=30',
        case
            when (
                select coalesce(max(total_equity), 0)
                from trading_paper_portfolio_snapshot
                where portfolio_id = 1
                  and run_id = 154
                  and snapshot_date = date '2026-04-23'
            ) > 0
            and (
                select coalesce(max(holding_count), 0)
                from trading_paper_portfolio_snapshot
                where portfolio_id = 1
                  and run_id = 154
                  and snapshot_date = date '2026-04-23'
            ) = 30
            then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C07_LATEST_RISK_DECISION_COUNT',
        'latest risk decision count should be 90',
        (
            select count(*)::text
            from risk_decision
            where run_id = 167
              and portfolio_id = 1
              and source_target_run_id = 160
              and adjusted_target_run_id = 166
        ),
        '90',
        case
            when (
                select count(*)
                from risk_decision
                where run_id = 167
                  and portfolio_id = 1
                  and source_target_run_id = 160
                  and adjusted_target_run_id = 166
            ) = 90 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C08_STRICT_REJECT_COUNT',
        'strict profile expected reject count should be 30',
        (
            select count(*)::text
            from risk_decision
            where run_id = 167
              and portfolio_id = 1
              and source_target_run_id = 160
              and adjusted_target_run_id = 166
              and decision_type = 'REJECT'
        ),
        '30',
        case
            when (
                select count(*)
                from risk_decision
                where run_id = 167
                  and portfolio_id = 1
                  and source_target_run_id = 160
                  and adjusted_target_run_id = 166
                  and decision_type = 'REJECT'
            ) = 30 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C09_STRICT_NO_WARN',
        'strict profile should have no WARN decisions',
        (
            select count(*)::text
            from risk_decision
            where run_id = 167
              and portfolio_id = 1
              and source_target_run_id = 160
              and adjusted_target_run_id = 166
              and decision_type = 'WARN'
        ),
        '0',
        case
            when (
                select count(*)
                from risk_decision
                where run_id = 167
                  and portfolio_id = 1
                  and source_target_run_id = 160
                  and adjusted_target_run_id = 166
                  and decision_type = 'WARN'
            ) = 0 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C10_STRICT_NO_ADJUST',
        'strict profile should have no ADJUST decisions',
        (
            select count(*)::text
            from risk_decision
            where run_id = 167
              and portfolio_id = 1
              and source_target_run_id = 160
              and adjusted_target_run_id = 166
              and decision_type = 'ADJUST'
        ),
        '0',
        case
            when (
                select count(*)
                from risk_decision
                where run_id = 167
                  and portfolio_id = 1
                  and source_target_run_id = 160
                  and adjusted_target_run_id = 166
                  and decision_type = 'ADJUST'
            ) = 0 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C11_ADJUSTED_TARGET_ZERO',
        'strict adjusted target quantity and amount should be zero',
        (
            select
                coalesce(sum(target_quantity), 0)::text || '/' ||
                coalesce(sum(target_amount), 0)::text
            from trading_paper_target_position
            where portfolio_id = 1
              and run_id = 166
        ),
        '0/0',
        case
            when (
                select coalesce(sum(target_quantity), 0)
                from trading_paper_target_position
                where portfolio_id = 1
                  and run_id = 166
            ) = 0
            and (
                select coalesce(sum(target_amount), 0)
                from trading_paper_target_position
                where portfolio_id = 1
                  and run_id = 166
            ) = 0
            then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C12_RISK_PROFILE_EXISTS',
        'risk profile should exist',
        (
            select count(*)::text
            from risk_profile
            where profile_code = 'paper_cn_a_risk3_strict_v1'
              and enabled = true
        ),
        '1',
        case
            when (
                select count(*)
                from risk_profile
                where profile_code = 'paper_cn_a_risk3_strict_v1'
                  and enabled = true
            ) = 1 then 'PASS'
            else 'FAIL'
        end
)
select *
from checks

union all

select
    'OVERALL' as check_code,
    'M8.6 acceptance overall status' as check_name,
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
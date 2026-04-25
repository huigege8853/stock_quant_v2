-- M8.5 Scheduler Adapter / Manual-to-Scheduled Ops Acceptance
-- stock_quant_v2
--
-- SQL 只验收调度入口依赖的数据库状态；
-- 本地模板文件和 PS1 手动执行结果由 PowerShell 验收。

with checks as (
    select
        'C01_NO_RUNNING_RUNS' as check_code,
        'no RUNNING ops_run before scheduler adapter' as check_name,
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
        'C02_LATEST_ORDER_SUCCESS',
        'latest order run is SUCCESS',
        (
            select status
            from ops_run
            where id = 146
        ),
        'SUCCESS',
        case
            when (
                select status
                from ops_run
                where id = 146
            ) = 'SUCCESS' then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C03_LATEST_FILL_SUCCESS',
        'latest fill run is SUCCESS',
        (
            select status
            from ops_run
            where id = 147
        ),
        'SUCCESS',
        case
            when (
                select status
                from ops_run
                where id = 147
            ) = 'SUCCESS' then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C04_LATEST_POSITION_SUCCESS',
        'latest position run is SUCCESS',
        (
            select status
            from ops_run
            where id = 153
        ),
        'SUCCESS',
        case
            when (
                select status
                from ops_run
                where id = 153
            ) = 'SUCCESS' then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C05_LATEST_SNAPSHOT_SUCCESS',
        'latest snapshot run is SUCCESS',
        (
            select status
            from ops_run
            where id = 154
        ),
        'SUCCESS',
        case
            when (
                select status
                from ops_run
                where id = 154
            ) = 'SUCCESS' then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C06_LATEST_TRADING_CHAIN_DATA_EXISTS',
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
        'C07_LATEST_RISK_CHAIN_DATA_EXISTS',
        'latest risk chain decision rows exist',
        (
            select count(*)::text
            from risk_decision
            where run_id = 167
              and source_target_run_id = 160
              and adjusted_target_run_id = 166
        ),
        '90',
        case
            when (
                select count(*)
                from risk_decision
                where run_id = 167
                  and source_target_run_id = 160
                  and adjusted_target_run_id = 166
            ) = 90 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C08_STRICT_PROFILE_REJECT_EXPECTED',
        'strict profile has expected 30 REJECT decisions',
        (
            select count(*)::text
            from risk_decision
            where run_id = 167
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
                  and source_target_run_id = 160
                  and adjusted_target_run_id = 166
                  and decision_type = 'REJECT'
            ) = 30 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C09_DAILY_OPS_SNAPSHOT_EXISTS',
        'daily ops snapshot exists',
        (
            select count(*)::text
            from trading_paper_portfolio_snapshot
            where run_id = 154
              and portfolio_id = 1
              and snapshot_date = date '2026-04-23'
        ),
        '1',
        case
            when (
                select count(*)
                from trading_paper_portfolio_snapshot
                where run_id = 154
                  and portfolio_id = 1
                  and snapshot_date = date '2026-04-23'
            ) = 1 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C10_DAILY_OPS_SNAPSHOT_EQUITY_POSITIVE',
        'daily ops snapshot total equity positive',
        (
            select coalesce(max(total_equity), 0)::text
            from trading_paper_portfolio_snapshot
            where run_id = 154
              and portfolio_id = 1
        ),
        '>0',
        case
            when (
                select coalesce(max(total_equity), 0)
                from trading_paper_portfolio_snapshot
                where run_id = 154
                  and portfolio_id = 1
            ) > 0 then 'PASS'
            else 'FAIL'
        end
)
select *
from checks

union all

select
    'OVERALL' as check_code,
    'M8.5 acceptance overall status' as check_name,
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
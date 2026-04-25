-- M8.4 Ops Hygiene / Stale Run Cleanup Acceptance
-- stock_quant_v2

with checks as (
    select
        'C01_NO_RUNNING_RUNS' as check_code,
        'ops_run should have no RUNNING rows after M8.4 cleanup' as check_name,
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
        'C02_STALE_EXISTS',
        'stale rows should exist after cleanup',
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
        'C03_SUCCESS_EXISTS',
        'success rows should exist after cleanup',
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
        'C04_LATEST_ORDER_SUCCESS',
        'latest order run should remain SUCCESS',
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
        'C05_LATEST_FILL_SUCCESS',
        'latest fill run should remain SUCCESS',
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
        'C06_LATEST_POSITION_SUCCESS',
        'latest position run should remain SUCCESS',
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
        'C07_LATEST_SNAPSHOT_SUCCESS',
        'latest snapshot run should remain SUCCESS',
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
        'C08_STALE_ORDER_PLACEHOLDER',
        'empty placeholder order run should be STALE',
        (
            select status
            from ops_run
            where id = 151
        ),
        'STALE',
        case
            when (
                select status
                from ops_run
                where id = 151
            ) = 'STALE' then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C09_STALE_FILL_PLACEHOLDER',
        'empty placeholder fill run should be STALE',
        (
            select status
            from ops_run
            where id = 152
        ),
        'STALE',
        case
            when (
                select status
                from ops_run
                where id = 152
            ) = 'STALE' then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C10_LATEST_TRADING_CHAIN_DATA_EXISTS',
        'latest trading chain data should still exist',
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
        'C11_LATEST_RISK_CHAIN_DATA_EXISTS',
        'latest risk chain data should still exist',
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
)
select *
from checks

union all

select
    'OVERALL' as check_code,
    'M8.4 acceptance overall status' as check_name,
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
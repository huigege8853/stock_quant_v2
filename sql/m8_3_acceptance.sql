-- M8.3 Daily Ops Orchestration / Scheduler Preparation Acceptance
-- stock_quant_v2
--
-- 验收目标：
-- 1. latest trading chain 完整
-- 2. latest risk chain 完整
-- 3. paper chain 数据完整
-- 4. risk decision 数据完整
-- 5. target diff 符合 strict profile 预期
-- 6. snapshot 可用于 daily ops
--
-- 当前验收参数：
-- portfolio_id = 1
-- trading_chain = 160 / 146 / 147 / 153 / 154
-- risk_chain = 167 / 160 / 166
-- risk_profile_code = paper_cn_a_risk3_strict_v1

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
        'paper_cn_a_risk3_strict_v1'::text as risk_profile_code
),
checks as (
    select
        'C01_LATEST_TARGET_EXISTS' as check_code,
        'latest target rows exist' as check_name,
        (
            select count(*)::text
            from trading_paper_target_position t, params p
            where t.portfolio_id = p.portfolio_id
              and t.run_id = p.target_run_id
        ) as actual_value,
        '30' as expected_value,
        case
            when (
                select count(*)
                from trading_paper_target_position t, params p
                where t.portfolio_id = p.portfolio_id
                  and t.run_id = p.target_run_id
            ) = 30 then 'PASS'
            else 'FAIL'
        end as status

    union all

    select
        'C02_LATEST_ORDER_EXISTS',
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
        'C03_LATEST_FILL_EXISTS',
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
        'C04_LATEST_POSITION_EXISTS',
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
        'C05_LATEST_SNAPSHOT_EXISTS',
        'latest snapshot exists',
        (
            select count(*)::text
            from trading_paper_portfolio_snapshot s, params p
            where s.portfolio_id = p.portfolio_id
              and s.run_id = p.snapshot_run_id
        ),
        '1',
        case
            when (
                select count(*)
                from trading_paper_portfolio_snapshot s, params p
                where s.portfolio_id = p.portfolio_id
                  and s.run_id = p.snapshot_run_id
            ) = 1 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C06_SNAPSHOT_TOTAL_EQUITY_POSITIVE',
        'daily ops snapshot total equity positive',
        (
            select coalesce(max(s.total_equity), 0)::text
            from trading_paper_portfolio_snapshot s, params p
            where s.portfolio_id = p.portfolio_id
              and s.run_id = p.snapshot_run_id
        ),
        '>0',
        case
            when (
                select coalesce(max(s.total_equity), 0)
                from trading_paper_portfolio_snapshot s, params p
                where s.portfolio_id = p.portfolio_id
                  and s.run_id = p.snapshot_run_id
            ) > 0 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C07_RISK_CHAIN_EXISTS',
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
        'C08_RISK_REJECT_EXPECTED',
        'strict profile reject count expected',
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
        'C09_NO_RISK_WARN',
        'strict profile has no WARN decision',
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
        'C10_NO_RISK_ADJUST',
        'strict profile has no ADJUST decision',
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
        'C11_TARGET_DIFF_EXPECTED_ZERO',
        'strict adjusted target quantity is zero',
        (
            select coalesce(sum(t.target_quantity), 0)::text
            from trading_paper_target_position t, params p
            where t.portfolio_id = p.portfolio_id
              and t.run_id = p.adjusted_target_run_id
        ),
        '0',
        case
            when (
                select coalesce(sum(t.target_quantity), 0)
                from trading_paper_target_position t, params p
                where t.portfolio_id = p.portfolio_id
                  and t.run_id = p.adjusted_target_run_id
            ) = 0 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C12_RISK_RUN_SUCCESS',
        'risk run success for daily ops',
        (
            select count(*)::text
            from ops_run r, params p
            where r.id = p.risk_run_id
              and r.status = 'SUCCESS'
        ),
        '1',
        case
            when (
                select count(*)
                from ops_run r, params p
                where r.id = p.risk_run_id
                  and r.status = 'SUCCESS'
            ) = 1 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C13_PROFILE_EXISTS',
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
    'M8.3 acceptance overall status' as check_name,
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
-- M8.2 Ops Report Export Center / Runbook Acceptance
-- stock_quant_v2
--
-- 注意：
-- SQL 只能验收导出报告所依赖的数据库事实；
-- 本地 artifacts 文件是否存在，由 PowerShell 文件验收命令完成。
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
        'C01_TARGET_EXISTS' as check_code,
        'target rows exist for report export' as check_name,
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
        'C02_ORDER_EXISTS',
        'order rows exist for report export',
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
        'C03_FILL_EXISTS',
        'fill rows exist for report export',
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
        'C04_POSITION_EXISTS',
        'position rows exist for report export',
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
        'C05_SNAPSHOT_EXISTS',
        'portfolio snapshot exists for report export',
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
        'C06_FILL_ORDER_JOIN',
        'all fill rows can join order rows',
        (
            select count(*)::text
            from trading_paper_fill f
            join trading_paper_order o
              on o.id = f.order_id
            join params p
              on p.portfolio_id = f.portfolio_id
            where f.run_id = p.fill_run_id
              and o.run_id = p.order_run_id
        ),
        '28',
        case
            when (
                select count(*)
                from trading_paper_fill f
                join trading_paper_order o
                  on o.id = f.order_id
                join params p
                  on p.portfolio_id = f.portfolio_id
                where f.run_id = p.fill_run_id
                  and o.run_id = p.order_run_id
            ) = 28 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C07_LATEST_SNAPSHOT_VALUE',
        'snapshot total equity is available',
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
        'C08_RISK_RUN_EXISTS',
        'risk run exists for run summary report',
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
        'C09_RISK_DECISION_EXISTS',
        'risk decision rows exist for daily ops report',
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
        'C10_RISK_REJECT_COUNT',
        'strict profile rejects 30 targets',
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
        'C11_TARGET_DIFF_ZERO',
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
        'C12_PROFILE_EXISTS',
        'risk profile exists for daily ops report',
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
    'M8.2 acceptance overall status' as check_name,
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
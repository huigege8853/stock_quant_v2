-- M8.1 Run Monitor + CLI Acceptance
-- stock_quant_v2
-- 验收对象：
-- 1) run 查询
-- 2) latest runs 自动链路识别
-- 3) paper chain 查询
-- 4) risk profile 查询
-- 5) risk decision 查询
-- 6) target diff 查询
--
-- 当前验收参数基于 M7-Risk final / M8.1 验证结果：
-- portfolio_id = 1
-- source_target_run_id = 160
-- adjusted_target_run_id = 166
-- risk_run_id = 167
-- target_run_id = 160
-- order_run_id = 146
-- fill_run_id = 147
-- position_run_id = 153
-- snapshot_run_id = 154
-- risk_profile_code = paper_cn_a_risk3_strict_v1

with params as (
    select
        1::bigint as portfolio_id,
        160::bigint as source_target_run_id,
        166::bigint as adjusted_target_run_id,
        167::bigint as risk_run_id,
        160::bigint as target_run_id,
        146::bigint as order_run_id,
        147::bigint as fill_run_id,
        153::bigint as position_run_id,
        154::bigint as snapshot_run_id,
        'paper_cn_a_risk3_strict_v1'::text as risk_profile_code
),
checks as (
    select
        'C01_RISK_RUN_EXISTS' as check_code,
        'risk run exists and SUCCESS' as check_name,
        (
            select count(*)::text
            from ops_run r, params p
            where r.id = p.risk_run_id
              and r.status = 'SUCCESS'
        ) as actual_value,
        '1' as expected_value,
        case
            when (
                select count(*)
                from ops_run r, params p
                where r.id = p.risk_run_id
                  and r.status = 'SUCCESS'
            ) = 1 then 'PASS'
            else 'FAIL'
        end as status

    union all

    select
        'C02_RISK_PROFILE_EXISTS',
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

    union all

    select
        'C03_RISK_PROFILE_RULE_COUNT',
        'risk3 strict profile has 3 enabled rules',
        (
            select count(*)::text
            from risk_profile rp
            join risk_profile_rule rpr
              on rpr.profile_id = rp.id
            join params p
              on p.risk_profile_code = rp.profile_code
            where rpr.enabled = true
        ),
        '3',
        case
            when (
                select count(*)
                from risk_profile rp
                join risk_profile_rule rpr
                  on rpr.profile_id = rp.id
                join params p
                  on p.risk_profile_code = rp.profile_code
                where rpr.enabled = true
            ) = 3 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C04_SOURCE_TARGET_EXISTS',
        'source target exists',
        (
            select count(*)::text
            from trading_paper_target_position t, params p
            where t.run_id = p.source_target_run_id
              and t.portfolio_id = p.portfolio_id
        ),
        '30',
        case
            when (
                select count(*)
                from trading_paper_target_position t, params p
                where t.run_id = p.source_target_run_id
                  and t.portfolio_id = p.portfolio_id
            ) = 30 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C05_ADJUSTED_TARGET_EXISTS',
        'adjusted target exists',
        (
            select count(*)::text
            from trading_paper_target_position t, params p
            where t.run_id = p.adjusted_target_run_id
              and t.portfolio_id = p.portfolio_id
        ),
        '30',
        case
            when (
                select count(*)
                from trading_paper_target_position t, params p
                where t.run_id = p.adjusted_target_run_id
                  and t.portfolio_id = p.portfolio_id
            ) = 30 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C06_ADJUSTED_TARGET_ZERO',
        'strict adjusted target quantity is zero',
        (
            select coalesce(sum(t.target_quantity), 0)::text
            from trading_paper_target_position t, params p
            where t.run_id = p.adjusted_target_run_id
              and t.portfolio_id = p.portfolio_id
        ),
        '0',
        case
            when (
                select coalesce(sum(t.target_quantity), 0)
                from trading_paper_target_position t, params p
                where t.run_id = p.adjusted_target_run_id
                  and t.portfolio_id = p.portfolio_id
            ) = 0 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C07_RISK_DECISION_COUNT',
        'risk decision count is 90',
        (
            select count(*)::text
            from risk_decision rd, params p
            where rd.run_id = p.risk_run_id
              and rd.source_target_run_id = p.source_target_run_id
              and rd.adjusted_target_run_id = p.adjusted_target_run_id
              and rd.portfolio_id = p.portfolio_id
        ),
        '90',
        case
            when (
                select count(*)
                from risk_decision rd, params p
                where rd.run_id = p.risk_run_id
                  and rd.source_target_run_id = p.source_target_run_id
                  and rd.adjusted_target_run_id = p.adjusted_target_run_id
                  and rd.portfolio_id = p.portfolio_id
            ) = 90 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C08_RISK_REJECT_COUNT',
        'risk reject count is 30',
        (
            select count(*)::text
            from risk_decision rd, params p
            where rd.run_id = p.risk_run_id
              and rd.source_target_run_id = p.source_target_run_id
              and rd.adjusted_target_run_id = p.adjusted_target_run_id
              and rd.portfolio_id = p.portfolio_id
              and rd.decision_type = 'REJECT'
        ),
        '30',
        case
            when (
                select count(*)
                from risk_decision rd, params p
                where rd.run_id = p.risk_run_id
                  and rd.source_target_run_id = p.source_target_run_id
                  and rd.adjusted_target_run_id = p.adjusted_target_run_id
                  and rd.portfolio_id = p.portfolio_id
                  and rd.decision_type = 'REJECT'
            ) = 30 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C09_R007_MISSING_INDUSTRY_COUNT',
        'R007 missing industry reject count is 30',
        (
            select count(*)::text
            from risk_decision rd, params p
            where rd.run_id = p.risk_run_id
              and rd.source_target_run_id = p.source_target_run_id
              and rd.adjusted_target_run_id = p.adjusted_target_run_id
              and rd.portfolio_id = p.portfolio_id
              and rd.reason_code = 'R007_MISSING_INDUSTRY'
              and rd.decision_type = 'REJECT'
        ),
        '30',
        case
            when (
                select count(*)
                from risk_decision rd, params p
                where rd.run_id = p.risk_run_id
                  and rd.source_target_run_id = p.source_target_run_id
                  and rd.adjusted_target_run_id = p.adjusted_target_run_id
                  and rd.portfolio_id = p.portfolio_id
                  and rd.reason_code = 'R007_MISSING_INDUSTRY'
                  and rd.decision_type = 'REJECT'
            ) = 30 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C10_ORDER_EXISTS',
        'paper order exists',
        (
            select count(*)::text
            from trading_paper_order o, params p
            where o.run_id = p.order_run_id
              and o.portfolio_id = p.portfolio_id
        ),
        '>0',
        case
            when (
                select count(*)
                from trading_paper_order o, params p
                where o.run_id = p.order_run_id
                  and o.portfolio_id = p.portfolio_id
            ) > 0 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C11_FILL_EXISTS',
        'paper fill exists',
        (
            select count(*)::text
            from trading_paper_fill f, params p
            where f.run_id = p.fill_run_id
              and f.portfolio_id = p.portfolio_id
        ),
        '>0',
        case
            when (
                select count(*)
                from trading_paper_fill f, params p
                where f.run_id = p.fill_run_id
                  and f.portfolio_id = p.portfolio_id
            ) > 0 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C12_POSITION_EXISTS',
        'paper position exists',
        (
            select count(*)::text
            from trading_paper_position pos, params p
            where pos.run_id = p.position_run_id
              and pos.portfolio_id = p.portfolio_id
        ),
        '>0',
        case
            when (
                select count(*)
                from trading_paper_position pos, params p
                where pos.run_id = p.position_run_id
                  and pos.portfolio_id = p.portfolio_id
            ) > 0 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C13_SNAPSHOT_EXISTS',
        'paper portfolio snapshot exists',
        (
            select count(*)::text
            from trading_paper_portfolio_snapshot s, params p
            where s.run_id = p.snapshot_run_id
              and s.portfolio_id = p.portfolio_id
        ),
        '1',
        case
            when (
                select count(*)
                from trading_paper_portfolio_snapshot s, params p
                where s.run_id = p.snapshot_run_id
                  and s.portfolio_id = p.portfolio_id
            ) = 1 then 'PASS'
            else 'FAIL'
        end

    union all

    select
        'C14_TARGET_DIFF_STRICT_ZERO',
        'strict risk target diff makes adjusted amount zero',
        (
            select
                (
                    coalesce((
                        select sum(a.target_amount)
                        from trading_paper_target_position a, params p
                        where a.run_id = p.adjusted_target_run_id
                          and a.portfolio_id = p.portfolio_id
                    ), 0)
                )::text
        ),
        '0',
        case
            when (
                coalesce((
                    select sum(a.target_amount)
                    from trading_paper_target_position a, params p
                    where a.run_id = p.adjusted_target_run_id
                      and a.portfolio_id = p.portfolio_id
                ), 0)
            ) = 0 then 'PASS'
            else 'FAIL'
        end
)
select *
from checks

union all

select
    'OVERALL' as check_code,
    'M8.1 acceptance overall status' as check_name,
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
-- m3_1_acceptance.sql
-- stock_quant_v2 | M3 acceptance SQL
-- 用途：
-- 1) 验收 M3 indicator / factor / feature / label 首链
-- 2) 验收 strict mode 下复权因子覆盖
-- 3) 验收最近一次 M3 run 状态
--
-- 建议执行方式：
-- psql -d <your_db> -f sql/m3_1_acceptance.sql
--
-- 默认逻辑：
-- - indicator / factor / feature 使用 core_daily_bar 最新 RAW 交易日
-- - label 使用“仍然有未来 10 个交易日”的最新 anchor_date
--
-- 如果你想固定日期，可把 params CTE 里的日期改成常量。

-- ============================================================
-- 0) 参数区：自动解析 M3 验收日期
-- ============================================================

with latest_trade_day as (
    select max(trade_date) as trade_date
    from core_daily_bar
    where price_adjust_type = 'RAW'
),
distinct_trade_days as (
    select distinct trade_date
    from core_daily_bar
    where price_adjust_type = 'RAW'
),
latest_label_anchor as (
    select trade_date as anchor_date
    from (
        select
            trade_date,
            lead(trade_date, 10) over (order by trade_date) as horizon_10_end_date
        from distinct_trade_days
    ) x
    where horizon_10_end_date is not null
    order by trade_date desc
    limit 1
),
params as (
    select
        (select trade_date from latest_trade_day) as m3_trade_date,
        (select anchor_date from latest_label_anchor) as m3_label_anchor_date
)
select
    'M3_ACCEPTANCE_PARAMS' as section,
    m3_trade_date,
    m3_label_anchor_date
from params;

-- ============================================================
-- 1) indicator 验收
-- ============================================================

with params as (
    with latest_trade_day as (
        select max(trade_date) as trade_date
        from core_daily_bar
        where price_adjust_type = 'RAW'
    )
    select trade_date as m3_trade_date
    from latest_trade_day
)
select
    i.trade_date,
    i.indicator_code,
    count(*) as row_count
from analytics_instrument_indicator_snapshot i
join params p on i.trade_date = p.m3_trade_date
group by i.trade_date, i.indicator_code
order by i.indicator_code;

with params as (
    with latest_trade_day as (
        select max(trade_date) as trade_date
        from core_daily_bar
        where price_adjust_type = 'RAW'
    )
    select trade_date as m3_trade_date
    from latest_trade_day
)
select
    i.indicator_code,
    count(*) as total_rows,
    sum(case when i.is_ready then 1 else 0 end) as ready_rows,
    sum(case when i.warmup_ready then 1 else 0 end) as warmup_ready_rows
from analytics_instrument_indicator_snapshot i
join params p on i.trade_date = p.m3_trade_date
group by i.indicator_code
order by i.indicator_code;

-- strict mode 下 forward_factor 覆盖检查
with params as (
    with latest_trade_day as (
        select max(trade_date) as trade_date
        from core_daily_bar
        where price_adjust_type = 'RAW'
    )
    select trade_date as m3_trade_date
    from latest_trade_day
)
select
    count(*) as total_bar_rows,
    sum(case when af.forward_factor is not null then 1 else 0 end) as matched_forward_factor_rows,
    sum(case when af.forward_factor is null then 1 else 0 end) as missing_forward_factor_rows
from core_daily_bar db
left join core_adjust_factor af
    on af.instrument_id = db.instrument_id
   and af.trade_date = db.trade_date
join params p
    on db.trade_date = p.m3_trade_date
where db.price_adjust_type = 'RAW';

-- latest trade day 对齐检查
with params as (
    with latest_trade_day as (
        select max(trade_date) as trade_date
        from core_daily_bar
        where price_adjust_type = 'RAW'
    )
    select trade_date as m3_trade_date
    from latest_trade_day
)
select
    'daily_bar_raw' as item,
    count(*) as row_count
from core_daily_bar db
join params p on db.trade_date = p.m3_trade_date
where db.price_adjust_type = 'RAW'

union all

select
    'adj_close_ready' as item,
    count(*) as row_count
from analytics_instrument_indicator_snapshot i
join params p on i.trade_date = p.m3_trade_date
where i.indicator_code = 'adj_close'
  and i.is_ready

union all

select
    'ret_20d_ready' as item,
    count(*) as row_count
from analytics_instrument_indicator_snapshot i
join params p on i.trade_date = p.m3_trade_date
where i.indicator_code = 'ret_20d'
  and i.is_ready
  and i.warmup_ready

order by item;

-- ============================================================
-- 2) factor 验收
-- ============================================================

with params as (
    with latest_trade_day as (
        select max(trade_date) as trade_date
        from core_daily_bar
        where price_adjust_type = 'RAW'
    )
    select trade_date as m3_trade_date
    from latest_trade_day
)
select
    f.trade_date,
    f.factor_code,
    count(*) as row_count
from analytics_instrument_factor_snapshot f
join params p on f.trade_date = p.m3_trade_date
group by f.trade_date, f.factor_code
order by f.factor_code;

with params as (
    with latest_trade_day as (
        select max(trade_date) as trade_date
        from core_daily_bar
        where price_adjust_type = 'RAW'
    )
    select trade_date as m3_trade_date
    from latest_trade_day
)
select
    f.factor_code,
    count(*) as total_rows,
    sum(case when f.is_ready then 1 else 0 end) as ready_rows
from analytics_instrument_factor_snapshot f
join params p on f.trade_date = p.m3_trade_date
group by f.factor_code
order by f.factor_code;

-- tie-rank 验收：tradability_score 相同值必须同 rank / same bucket
with params as (
    with latest_trade_day as (
        select max(trade_date) as trade_date
        from core_daily_bar
        where price_adjust_type = 'RAW'
    )
    select trade_date as m3_trade_date
    from latest_trade_day
)
select
    f.raw_value,
    f.rank_value,
    f.bucket_value,
    count(*) as row_count
from analytics_instrument_factor_snapshot f
join params p on f.trade_date = p.m3_trade_date
where f.factor_code = 'tradability_score'
group by f.raw_value, f.rank_value, f.bucket_value
order by f.raw_value, f.rank_value;

-- ============================================================
-- 3) feature 验收
-- ============================================================

with params as (
    with latest_trade_day as (
        select max(trade_date) as trade_date
        from core_daily_bar
        where price_adjust_type = 'RAW'
    )
    select trade_date as m3_trade_date
    from latest_trade_day
)
select
    s.trade_date,
    s.feature_set_code,
    s.feature_code,
    count(*) as row_count
from analytics_feature_snapshot s
join params p on s.trade_date = p.m3_trade_date
group by s.trade_date, s.feature_set_code, s.feature_code
order by s.feature_code;

with params as (
    with latest_trade_day as (
        select max(trade_date) as trade_date
        from core_daily_bar
        where price_adjust_type = 'RAW'
    )
    select trade_date as m3_trade_date
    from latest_trade_day
)
select
    s.feature_code,
    count(*) as total_rows,
    sum(case when s.sample_status = 'ready' then 1 else 0 end) as ready_rows,
    sum(case when s.sample_status = 'missing' then 1 else 0 end) as missing_rows
from analytics_feature_snapshot s
join params p on s.trade_date = p.m3_trade_date
group by s.feature_code
order by s.feature_code;

-- ============================================================
-- 4) label 验收
-- ============================================================

with distinct_trade_days as (
    select distinct trade_date
    from core_daily_bar
    where price_adjust_type = 'RAW'
),
latest_label_anchor as (
    select trade_date as anchor_date
    from (
        select
            trade_date,
            lead(trade_date, 10) over (order by trade_date) as horizon_10_end_date
        from distinct_trade_days
    ) x
    where horizon_10_end_date is not null
    order by trade_date desc
    limit 1
)
select
    l.anchor_date,
    l.label_code,
    count(*) as row_count
from analytics_label_snapshot l
join latest_label_anchor a on l.anchor_date = a.anchor_date
group by l.anchor_date, l.label_code
order by l.label_code;

with distinct_trade_days as (
    select distinct trade_date
    from core_daily_bar
    where price_adjust_type = 'RAW'
),
latest_label_anchor as (
    select trade_date as anchor_date
    from (
        select
            trade_date,
            lead(trade_date, 10) over (order by trade_date) as horizon_10_end_date
        from distinct_trade_days
    ) x
    where horizon_10_end_date is not null
    order by trade_date desc
    limit 1
)
select
    l.label_code,
    count(*) as total_rows,
    sum(case when l.is_censored then 1 else 0 end) as censored_rows,
    sum(case when not l.is_censored then 1 else 0 end) as uncensored_rows
from analytics_label_snapshot l
join latest_label_anchor a on l.anchor_date = a.anchor_date
group by l.label_code
order by l.label_code;

with distinct_trade_days as (
    select distinct trade_date
    from core_daily_bar
    where price_adjust_type = 'RAW'
),
latest_label_anchor as (
    select trade_date as anchor_date
    from (
        select
            trade_date,
            lead(trade_date, 10) over (order by trade_date) as horizon_10_end_date
        from distinct_trade_days
    ) x
    where horizon_10_end_date is not null
    order by trade_date desc
    limit 1
)
select
    l.label_code,
    sum(case when l.label_value_numeric is not null then 1 else 0 end) as numeric_value_rows,
    sum(case when l.label_value_class is not null then 1 else 0 end) as class_value_rows
from analytics_label_snapshot l
join latest_label_anchor a on l.anchor_date = a.anchor_date
group by l.label_code
order by l.label_code;

-- label 抽样
with distinct_trade_days as (
    select distinct trade_date
    from core_daily_bar
    where price_adjust_type = 'RAW'
),
latest_label_anchor as (
    select trade_date as anchor_date
    from (
        select
            trade_date,
            lead(trade_date, 10) over (order by trade_date) as horizon_10_end_date
        from distinct_trade_days
    ) x
    where horizon_10_end_date is not null
    order by trade_date desc
    limit 1
)
select
    l.instrument_id,
    l.label_code,
    l.label_value_numeric,
    l.label_value_class,
    l.horizon_end_date,
    l.is_censored,
    l.leakage_checked
from analytics_label_snapshot l
join latest_label_anchor a on l.anchor_date = a.anchor_date
order by l.instrument_id, l.label_code
limit 40;

-- ============================================================
-- 5) M3 definition 验收
-- ============================================================

select 'meta_factor_definition' as table_name, count(*) as row_count
from meta_factor_definition

union all
select 'meta_feature_definition' as table_name, count(*) as row_count
from meta_feature_definition

union all
select 'meta_feature_set_definition' as table_name, count(*) as row_count
from meta_feature_set_definition

union all
select 'meta_indicator_definition' as table_name, count(*) as row_count
from meta_indicator_definition

union all
select 'meta_label_definition' as table_name, count(*) as row_count
from meta_label_definition
order by table_name;

-- ============================================================
-- 6) 最近 M3 run 状态验收
-- ============================================================

select
    id,
    run_uid,
    run_type,
    run_name,
    status,
    trigger_type,
    requested_at,
    started_at,
    ended_at,
    error_message
from ops_run
where run_name in (
    'bootstrap_m3_indicator_chain',
    'bootstrap_m3_factor_chain',
    'bootstrap_m3_feature_chain',
    'bootstrap_m3_label_chain'
)
order by id desc
limit 20;

-- ============================================================
-- 7) stale RUNNING 观察（不自动清理）
-- ============================================================

select
    id,
    run_type,
    run_name,
    status,
    requested_at,
    started_at,
    ended_at,
    now() - started_at as running_duration,
    error_message
from ops_run
where status = 'RUNNING'
order by started_at asc;

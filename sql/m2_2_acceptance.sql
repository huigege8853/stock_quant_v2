-- =========================================================
-- M2.2 行情域稳定化验收 SQL
-- 项目：stock_quant_v2
-- 目标：
-- 1. 验证 data_sync_run / data_batch / data_quality_issue
-- 2. 验证 instrument / trading_calendar / daily_bar /
--    adjust_factor / market_breadth / market_index_bar
-- 3. 验证 raw/staging/core 行数闭环
-- 4. 检查 stale RUNNING 脏记录
-- =========================================================


-- =========================================================
-- A. 当前连接与迁移状态
-- =========================================================

SELECT current_database() AS current_database, current_schema() AS current_schema;

SELECT version_num
FROM alembic_version;


-- =========================================================
-- B. 最近运行总览
-- =========================================================

SELECT
    id,
    sync_job_code,
    dataset_code,
    status,
    request_params,
    stats_json,
    started_at,
    finished_at
FROM data_sync_run
ORDER BY id DESC
LIMIT 30;


-- =========================================================
-- C. 分主题最近运行
-- =========================================================

-- instrument
SELECT
    id,
    sync_job_code,
    dataset_code,
    status,
    request_params,
    stats_json,
    started_at,
    finished_at
FROM data_sync_run
WHERE dataset_code = 'instrument'
ORDER BY id DESC
LIMIT 10;

-- trading_calendar
SELECT
    id,
    sync_job_code,
    dataset_code,
    status,
    request_params,
    stats_json,
    started_at,
    finished_at
FROM data_sync_run
WHERE dataset_code = 'trading_calendar'
ORDER BY id DESC
LIMIT 10;

-- daily_bar
SELECT
    id,
    sync_job_code,
    dataset_code,
    status,
    request_params,
    stats_json,
    started_at,
    finished_at
FROM data_sync_run
WHERE dataset_code = 'daily_bar'
ORDER BY id DESC
LIMIT 10;

-- adjust_factor
SELECT
    id,
    sync_job_code,
    dataset_code,
    status,
    request_params,
    stats_json,
    started_at,
    finished_at
FROM data_sync_run
WHERE dataset_code = 'adjust_factor'
ORDER BY id DESC
LIMIT 10;

-- market_breadth
SELECT
    id,
    sync_job_code,
    dataset_code,
    status,
    request_params,
    stats_json,
    started_at,
    finished_at
FROM data_sync_run
WHERE dataset_code = 'market_breadth'
ORDER BY id DESC
LIMIT 10;

-- market_index_bar
SELECT
    id,
    sync_job_code,
    dataset_code,
    status,
    request_params,
    stats_json,
    started_at,
    finished_at
FROM data_sync_run
WHERE dataset_code = 'market_index_bar'
ORDER BY id DESC
LIMIT 10;


-- =========================================================
-- D. 最近 batch 与 checkpoint
-- =========================================================

SELECT
    id,
    data_sync_run_id,
    batch_no,
    batch_key,
    status,
    checkpoint_json,
    error_message,
    started_at,
    finished_at
FROM data_batch
ORDER BY id DESC
LIMIT 30;

-- 指定日期 batch
SELECT
    id,
    data_sync_run_id,
    batch_no,
    batch_key,
    status,
    checkpoint_json,
    error_message
FROM data_batch
WHERE batch_key IN ('ALL', '2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05', '2024-01-10')
ORDER BY id DESC;


-- =========================================================
-- E. 质量问题总览
-- =========================================================

SELECT
    id,
    data_sync_run_id,
    batch_id,
    dataset_code,
    issue_code,
    severity,
    business_key,
    symbol,
    provider_name,
    issue_detail,
    created_at
FROM data_quality_issue
ORDER BY id DESC
LIMIT 100;

-- 各主题质量问题聚合
SELECT
    dataset_code,
    issue_code,
    severity,
    COUNT(*) AS cnt
FROM data_quality_issue
GROUP BY dataset_code, issue_code, severity
ORDER BY dataset_code, cnt DESC, issue_code;

-- instrument 最近一次运行的质量问题
SELECT
    id,
    data_sync_run_id,
    batch_id,
    issue_code,
    severity,
    business_key,
    symbol,
    provider_name,
    issue_detail,
    created_at
FROM data_quality_issue
WHERE dataset_code = 'instrument'
ORDER BY id DESC
LIMIT 100;


-- =========================================================
-- F. 主题级验收重点
-- =========================================================

-- F1. instrument 最新运行
SELECT
    id,
    status,
    stats_json ->> 'selected_provider' AS selected_provider,
    (stats_json ->> 'input_rows')::int AS input_rows,
    (stats_json ->> 'core_upsert_rows')::int AS core_upsert_rows,
    (stats_json ->> 'error_rows')::int AS error_rows
FROM data_sync_run
WHERE dataset_code = 'instrument'
ORDER BY id DESC
LIMIT 5;

-- F2. trading_calendar 最新运行
SELECT
    id,
    status,
    request_params,
    stats_json
FROM data_sync_run
WHERE dataset_code = 'trading_calendar'
ORDER BY id DESC
LIMIT 5;

-- F3. daily_bar 最新运行
SELECT
    id,
    status,
    request_params,
    stats_json
FROM data_sync_run
WHERE dataset_code = 'daily_bar'
ORDER BY id DESC
LIMIT 5;

-- F4. adjust_factor 最新运行
SELECT
    id,
    status,
    request_params,
    stats_json
FROM data_sync_run
WHERE dataset_code = 'adjust_factor'
ORDER BY id DESC
LIMIT 5;

-- F5. market_breadth 最新运行
SELECT
    id,
    status,
    request_params,
    stats_json
FROM data_sync_run
WHERE dataset_code = 'market_breadth'
ORDER BY id DESC
LIMIT 5;

-- F6. market_index_bar 最新运行
SELECT
    id,
    status,
    request_params,
    stats_json
FROM data_sync_run
WHERE dataset_code = 'market_index_bar'
ORDER BY id DESC
LIMIT 5;


-- =========================================================
-- G. priority / provider 口径检查
-- =========================================================

-- 检查 request_params 里 provider 是否落库
SELECT
    id,
    dataset_code,
    request_params
FROM data_sync_run
WHERE dataset_code IN (
    'instrument',
    'trading_calendar',
    'daily_bar',
    'adjust_factor',
    'market_index_bar'
)
ORDER BY id DESC
LIMIT 20;

-- 检查 adjust_factor 是否已独立 priority（不再复用 daily_bar）
SELECT
    id,
    dataset_code,
    request_params
FROM data_sync_run
WHERE dataset_code = 'adjust_factor'
ORDER BY id DESC
LIMIT 10;

-- 检查是否存在 tushare 配置痕迹
SELECT
    id,
    dataset_code,
    request_params
FROM data_sync_run
WHERE request_params::text ILIKE '%tushare%'
ORDER BY id DESC
LIMIT 30;

-- 检查 checkpoint 中是否存在 skipped / disabled_by_config
SELECT
    id,
    batch_key,
    checkpoint_json
FROM data_batch
WHERE checkpoint_json::text ILIKE '%skipped%'
   OR checkpoint_json::text ILIKE '%disabled_by_config%'
ORDER BY id DESC
LIMIT 30;


-- =========================================================
-- H. 表行数核对
-- =========================================================

SELECT 'meta_instrument' AS table_name, COUNT(*) AS row_count FROM meta_instrument
UNION ALL
SELECT 'meta_trading_calendar', COUNT(*) FROM meta_trading_calendar
UNION ALL
SELECT 'raw_daily_bar', COUNT(*) FROM raw_daily_bar
UNION ALL
SELECT 'stg_daily_bar', COUNT(*) FROM stg_daily_bar
UNION ALL
SELECT 'core_daily_bar', COUNT(*) FROM core_daily_bar
UNION ALL
SELECT 'raw_adjust_factor', COUNT(*) FROM raw_adjust_factor
UNION ALL
SELECT 'stg_adjust_factor', COUNT(*) FROM stg_adjust_factor
UNION ALL
SELECT 'core_adjust_factor', COUNT(*) FROM core_adjust_factor
UNION ALL
SELECT 'core_market_breadth', COUNT(*) FROM core_market_breadth
UNION ALL
SELECT 'raw_market_index', COUNT(*) FROM raw_market_index
UNION ALL
SELECT 'stg_market_index', COUNT(*) FROM stg_market_index
UNION ALL
SELECT 'market_index_bar', COUNT(*) FROM market_index_bar
ORDER BY table_name;


-- =========================================================
-- I. 关键日期样本核对
-- =========================================================

-- daily_bar 指定日期行数
SELECT
    trade_date,
    COUNT(*) AS row_count
FROM core_daily_bar
WHERE trade_date BETWEEN DATE '2024-01-02' AND DATE '2024-01-05'
GROUP BY trade_date
ORDER BY trade_date;

-- adjust_factor 指定日期行数
SELECT
    trade_date,
    COUNT(*) AS row_count
FROM core_adjust_factor
WHERE trade_date BETWEEN DATE '2024-01-02' AND DATE '2024-01-05'
GROUP BY trade_date
ORDER BY trade_date;

-- market_breadth 指定日期行数
SELECT
    trade_date,
    COUNT(*) AS row_count
FROM core_market_breadth
WHERE trade_date BETWEEN DATE '2024-01-02' AND DATE '2024-01-05'
GROUP BY trade_date
ORDER BY trade_date;

-- market_index_bar 指定日期行数
SELECT
    trade_date,
    COUNT(*) AS row_count
FROM market_index_bar
WHERE trade_date BETWEEN DATE '2024-01-02' AND DATE '2024-01-05'
GROUP BY trade_date
ORDER BY trade_date;


-- =========================================================
-- J. 一致性核对
-- =========================================================

-- core_daily_bar 同一 instrument_id + trade_date + price_adjust_type 是否重复
SELECT
    instrument_id,
    trade_date,
    price_adjust_type,
    COUNT(*) AS cnt
FROM core_daily_bar
GROUP BY instrument_id, trade_date, price_adjust_type
HAVING COUNT(*) > 1
ORDER BY cnt DESC, instrument_id, trade_date
LIMIT 50;

-- core_adjust_factor 同一 instrument_id + trade_date 是否重复
SELECT
    instrument_id,
    trade_date,
    COUNT(*) AS cnt
FROM core_adjust_factor
GROUP BY instrument_id, trade_date
HAVING COUNT(*) > 1
ORDER BY cnt DESC, instrument_id, trade_date
LIMIT 50;

-- market_index_bar 同一 market_index_id + trade_date 是否重复
SELECT
    market_index_id,
    trade_date,
    COUNT(*) AS cnt
FROM market_index_bar
GROUP BY market_index_id, trade_date
HAVING COUNT(*) > 1
ORDER BY cnt DESC, market_index_id, trade_date
LIMIT 50;


-- =========================================================
-- K. stale RUNNING 检查
-- =========================================================

SELECT
    id,
    sync_job_code,
    dataset_code,
    status,
    started_at,
    finished_at
FROM data_sync_run
WHERE status = 'RUNNING'
ORDER BY id DESC;

SELECT
    id,
    data_sync_run_id,
    batch_key,
    status,
    started_at,
    finished_at
FROM data_batch
WHERE status = 'RUNNING'
ORDER BY id DESC;


-- =========================================================
-- L. 必要时人工关闭 stale RUNNING（手动执行，默认注释）
-- =========================================================

-- UPDATE data_sync_run
-- SET status = 'FAILED',
--     stats_json = jsonb_build_object('error', 'manually closed stale running record'),
--     finished_at = now()
-- WHERE status = 'RUNNING';

-- UPDATE data_batch
-- SET status = 'FAILED',
--     error_message = 'manually closed stale running batch',
--     finished_at = now()
-- WHERE status = 'RUNNING';


-- =========================================================
-- M. M2.2 阶段验收建议标准（人工判断）
-- =========================================================
-- 1. instrument 最新运行应 SUCCESS，且 error_rows = 0
-- 2. trading_calendar / daily_bar / adjust_factor /
--    market_breadth / market_index_bar 最新运行应 SUCCESS 或
--    在可解释范围内 PARTIAL
-- 3. daily_bar provider 应以 baostock 为主
-- 4. market_index_bar provider 应以 sina 为主，baostock 可 empty
-- 5. adjust_factor 应使用独立 priority
-- 6. stale RUNNING 记录应为 0
-- 7. 关键 core 表不应出现重复主业务键
-- =========================================================
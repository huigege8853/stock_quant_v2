-- =========================================
-- M4.1 acceptance
-- alpha_selection:v1 / signal_v1
-- =========================================

-- 1. strategy_definition 是否存在
SELECT
    id,
    strategy_code,
    strategy_name,
    strategy_type,
    engine_type,
    lifecycle_status
FROM strategy_definition
WHERE strategy_code = 'alpha_selection';


-- 2. strategy_version 是否存在且 current
SELECT
    sv.id,
    sd.strategy_code,
    sv.version_code,
    sv.version_no,
    sv.is_current,
    sv.lifecycle_status,
    sv.output_contract_version,
    sv.implementation_ref
FROM strategy_version sv
JOIN strategy_definition sd
    ON sd.id = sv.strategy_definition_id
WHERE sd.strategy_code = 'alpha_selection'
ORDER BY sv.version_no;


-- 3. parameter_schema 是否存在
SELECT
    sps.id,
    sps.strategy_version_id,
    sps.schema_version_code,
    sps.parameter_schema_json,
    sps.example_payload_json
FROM strategy_parameter_schema sps
JOIN strategy_version sv
    ON sv.id = sps.strategy_version_id
JOIN strategy_definition sd
    ON sd.id = sv.strategy_definition_id
WHERE sd.strategy_code = 'alpha_selection'
ORDER BY sps.id;


-- 4. 指定 as_of_date 的 signal 数量
SELECT
    ss.as_of_date,
    ss.effective_date,
    COUNT(*) AS signal_count
FROM strategy_signal ss
JOIN strategy_version sv
    ON sv.id = ss.strategy_version_id
JOIN strategy_definition sd
    ON sd.id = sv.strategy_definition_id
WHERE sd.strategy_code = 'alpha_selection'
  AND sv.version_code = 'v1'
  AND ss.as_of_date = DATE '2024-03-29'
GROUP BY ss.as_of_date, ss.effective_date
ORDER BY ss.as_of_date, ss.effective_date;


-- 5. signal 基本字段分布
SELECT
    subject_type,
    signal_role,
    signal_side,
    signal_action,
    reason_code,
    COUNT(*) AS row_count
FROM strategy_signal
WHERE as_of_date = DATE '2024-03-29'
GROUP BY
    subject_type,
    signal_role,
    signal_side,
    signal_action,
    reason_code
ORDER BY row_count DESC;


-- 6. top 30 signal 明细
SELECT
    ss.id,
    ss.run_id,
    ss.strategy_version_id,
    ss.as_of_date,
    ss.effective_date,
    ss.instrument_id,
    ss.subject_key,
    ss.raw_score,
    ss.normalized_score,
    ss.confidence_score,
    ss.rank_in_batch,
    ss.universe_size,
    ss.reason_code,
    ss.parameter_payload_json
FROM strategy_signal ss
JOIN strategy_version sv
    ON sv.id = ss.strategy_version_id
JOIN strategy_definition sd
    ON sd.id = sv.strategy_definition_id
WHERE sd.strategy_code = 'alpha_selection'
  AND sv.version_code = 'v1'
  AND ss.as_of_date = DATE '2024-03-29'
ORDER BY ss.rank_in_batch, ss.id;


-- 7. effective_date 是否全为下一交易日（此处用 2024-04-01 做验收）
SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (WHERE effective_date = DATE '2024-04-01') AS correct_effective_date_rows,
    COUNT(*) FILTER (WHERE effective_date <> DATE '2024-04-01') AS wrong_effective_date_rows
FROM strategy_signal ss
JOIN strategy_version sv
    ON sv.id = ss.strategy_version_id
JOIN strategy_definition sd
    ON sd.id = sv.strategy_definition_id
WHERE sd.strategy_code = 'alpha_selection'
  AND sv.version_code = 'v1'
  AND ss.as_of_date = DATE '2024-03-29';


-- 8. signal 是否都挂到了 ops_run
SELECT
    ss.run_id,
    r.run_type,
    r.run_name,
    r.status,
    COUNT(*) AS signal_count
FROM strategy_signal ss
JOIN ops_run r
    ON r.id = ss.run_id
JOIN strategy_version sv
    ON sv.id = ss.strategy_version_id
JOIN strategy_definition sd
    ON sd.id = sv.strategy_definition_id
WHERE sd.strategy_code = 'alpha_selection'
  AND sv.version_code = 'v1'
  AND ss.as_of_date = DATE '2024-03-29'
GROUP BY
    ss.run_id,
    r.run_type,
    r.run_name,
    r.status
ORDER BY ss.run_id DESC;


-- 9. signal 是否都挂到了 instrument
SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (WHERE instrument_id IS NOT NULL) AS with_instrument_id_rows,
    COUNT(*) FILTER (WHERE instrument_id IS NULL) AS null_instrument_id_rows
FROM strategy_signal ss
JOIN strategy_version sv
    ON sv.id = ss.strategy_version_id
JOIN strategy_definition sd
    ON sd.id = sv.strategy_definition_id
WHERE sd.strategy_code = 'alpha_selection'
  AND sv.version_code = 'v1'
  AND ss.as_of_date = DATE '2024-03-29';


-- 10. strategy_signal 不应出现“同一 run 内重复 subject/action”
SELECT
    run_id,
    strategy_version_id,
    as_of_date,
    subject_key,
    signal_action,
    COUNT(*) AS dup_count
FROM strategy_signal
GROUP BY
    run_id,
    strategy_version_id,
    as_of_date,
    subject_key,
    signal_action
HAVING COUNT(*) > 1
ORDER BY dup_count DESC;


-- 11. score 排名是否单调
SELECT
    rank_in_batch,
    raw_score,
    normalized_score,
    confidence_score
FROM strategy_signal ss
JOIN strategy_version sv
    ON sv.id = ss.strategy_version_id
JOIN strategy_definition sd
    ON sd.id = sv.strategy_definition_id
WHERE sd.strategy_code = 'alpha_selection'
  AND sv.version_code = 'v1'
  AND ss.as_of_date = DATE '2024-03-29'
ORDER BY rank_in_batch, raw_score DESC;


-- 12. 当前 strategy_version 只应有一个 is_current=true
SELECT
    sd.strategy_code,
    COUNT(*) FILTER (WHERE sv.is_current = true) AS current_true_count
FROM strategy_version sv
JOIN strategy_definition sd
    ON sd.id = sv.strategy_definition_id
GROUP BY sd.strategy_code
ORDER BY sd.strategy_code;
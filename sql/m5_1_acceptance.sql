-- M5.1 / M5.3 acceptance
-- Research core + screen first chain acceptance

-- 1. M5 core tables exist
select
    table_name
from information_schema.tables
where table_schema = 'public'
  and table_name in (
      'research_execution_assumption_profile',
      'research_benchmark_definition',
      'research_screen_request',
      'research_screen_result',
      'research_backtest_request',
      'research_backtest_result',
      'ops_run_metric_snapshot',
      'ops_run_series_snapshot',
      'ops_run_artifact'
  )
order by table_name;


-- 2. Default execution assumption profile seeded
select
    id,
    profile_code,
    version_code,
    profile_name,
    market_code,
    asset_class,
    frequency,
    commission_model,
    commission_rate,
    min_commission,
    stamp_duty_rate,
    transfer_fee_rate,
    slippage_model,
    slippage_bps,
    price_fill_rule,
    volume_fill_rule,
    t_plus_rule,
    lot_size,
    allow_fractional_share,
    limit_up_down_rule,
    suspend_rule,
    cash_rule,
    is_active
from research_execution_assumption_profile
where profile_code = 'cn_a_daily_default'
  and version_code = 'v1';


-- 3. Benchmark intentionally not seeded by default
select
    count(*) as benchmark_definition_count
from research_benchmark_definition;


-- 4. Latest M5 screen request
select
    id,
    run_id,
    strategy_version_id,
    signal_lookup_mode,
    source_signal_run_id,
    as_of_date,
    effective_date,
    max_count,
    include_reason_codes,
    request_payload,
    created_at
from research_screen_request
order by id desc
limit 5;


-- 5. Latest M5 screen result
select
    id,
    run_id,
    screen_request_id,
    signal_run_id,
    as_of_date,
    effective_date,
    eligible_universe_size,
    selected_count,
    score_min,
    score_max,
    round(score_avg, 8) as score_avg_rounded,
    score_avg as score_avg_raw,
    result_status,
    result_summary,
    completed_at
from research_screen_result
order by id desc
limit 5;


-- 6. Latest screen metrics written to unified run metric snapshot
select
    run_id,
    metric_namespace,
    metric_code,
    metric_value_numeric,
    metric_value_text,
    dimension_type,
    dimension_key,
    sequence_no,
    created_at
from ops_run_metric_snapshot
where metric_namespace = 'screen'
order by run_id desc, sequence_no asc
limit 20;


-- 7. Acceptance check for the known first chain
select
    case
        when selected_count = 30
         and eligible_universe_size = 5027
         and score_min = 0.78414561
         and score_max = 0.84932365
         and round(score_avg, 8) = 0.80061650
         and result_status = 'SUCCESS'
        then 'PASS'
        else 'FAIL'
    end as m5_screen_first_chain_acceptance,
    run_id,
    screen_request_id,
    signal_run_id,
    eligible_universe_size,
    selected_count,
    score_min,
    score_max,
    round(score_avg, 8) as score_avg_rounded,
    result_status
from research_screen_result
where signal_run_id = 53
  and as_of_date = date '2024-03-29'
  and effective_date = date '2024-04-01'
order by id desc
limit 1;

-- 8. Latest M5 backtest request skeleton
select
    id,
    run_id,
    strategy_version_id,
    screen_request_id,
    source_signal_run_id,
    execution_assumption_profile_id,
    benchmark_definition_id,
    start_date,
    end_date,
    initial_cash,
    rebalance_frequency,
    signal_effective_mode,
    portfolio_construction_mode,
    engine_code,
    engine_payload,
    request_payload,
    created_at
from research_backtest_request
order by id desc
limit 5;


-- 9. Backtest request should bind execution assumption profile
select
    br.id as backtest_request_id,
    br.run_id,
    br.strategy_version_id,
    br.source_signal_run_id,
    br.screen_request_id,
    ep.profile_code,
    ep.version_code,
    ep.profile_name,
    ep.price_fill_rule,
    ep.commission_rate,
    ep.slippage_bps,
    br.initial_cash,
    br.engine_code
from research_backtest_request br
join research_execution_assumption_profile ep
  on br.execution_assumption_profile_id = ep.id
order by br.id desc
limit 5;


-- 10. M5.4 backtest request skeleton acceptance
select
    case
        when br.strategy_version_id = 1
         and br.source_signal_run_id = 53
         and br.screen_request_id = 3
         and ep.profile_code = 'cn_a_daily_default'
         and ep.version_code = 'v1'
         and br.benchmark_definition_id is null
         and br.initial_cash = 10000000
         and br.rebalance_frequency = 'DAILY'
         and br.signal_effective_mode = 'EFFECTIVE_DATE'
         and br.portfolio_construction_mode = 'EQUAL_WEIGHT_TOP_N'
         and br.engine_code = 'backtrader'
        then 'PASS'
        else 'FAIL'
    end as m5_backtest_request_skeleton_acceptance,
    br.id as backtest_request_id,
    br.run_id,
    br.strategy_version_id,
    br.source_signal_run_id,
    br.screen_request_id,
    br.execution_assumption_profile_id,
    ep.profile_code || ':' || ep.version_code as execution_assumption_profile,
    br.benchmark_definition_id,
    br.start_date,
    br.end_date,
    br.initial_cash,
    br.rebalance_frequency,
    br.signal_effective_mode,
    br.portfolio_construction_mode,
    br.engine_code
from research_backtest_request br
join research_execution_assumption_profile ep
  on br.execution_assumption_profile_id = ep.id
where br.source_signal_run_id = 53
  and br.screen_request_id = 3
  and br.start_date = date '2024-04-01'
  and br.end_date = date '2024-12-31'
order by br.id desc
limit 1;


-- 11. Confirm no backtest_result has been produced in skeleton stage
select
    count(*) as backtest_result_count
from research_backtest_result;


-- 12. Latest M5 backtest ops_run
select
    id,
    run_uid,
    run_type,
    run_name,
    status,
    trigger_type,
    started_at,
    completed_at,
    created_at,
    updated_at
from ops_run
where run_type = 'backtest'
order by id desc
limit 5;

-- 13. Latest M5 backtest result skeleton
select
    id,
    run_id,
    backtest_request_id,
    result_status,
    start_date,
    end_date,
    trading_days,
    initial_cash,
    final_equity,
    total_return,
    annual_return,
    benchmark_return,
    excess_return,
    max_drawdown,
    sharpe_ratio,
    volatility,
    win_rate,
    turnover_avg,
    order_count,
    trade_count,
    result_summary,
    completed_at
from research_backtest_result
order by id desc
limit 5;


-- 14. Latest backtest metrics in unified run metric snapshot
select
    run_id,
    metric_namespace,
    metric_code,
    metric_value_numeric,
    metric_value_text,
    dimension_type,
    dimension_key,
    sequence_no,
    created_at
from ops_run_metric_snapshot
where metric_namespace = 'backtest'
order by run_id desc, sequence_no asc
limit 30;


-- 15. M5.5 backtest result skeleton acceptance
select
    case
        when br.source_signal_run_id = 53
         and br.screen_request_id = 3
         and bres.result_status = 'EMPTY'
         and bres.initial_cash = 10000000
         and bres.final_equity is null
         and bres.order_count = 0
         and bres.trade_count = 0
        then 'PASS'
        else 'FAIL'
    end as m5_backtest_result_skeleton_acceptance,
    br.id as backtest_request_id,
    bres.id as backtest_result_id,
    br.run_id,
    br.source_signal_run_id,
    br.screen_request_id,
    bres.result_status,
    bres.initial_cash,
    bres.final_equity,
    bres.order_count,
    bres.trade_count,
    bres.result_summary
from research_backtest_request br
join research_backtest_result bres
  on br.run_id = bres.run_id
where br.source_signal_run_id = 53
  and br.screen_request_id = 3
  and br.start_date = date '2024-04-01'
  and br.end_date = date '2024-12-31'
order by bres.id desc
limit 1;


-- 16. M5.5 metric acceptance
select
    case
        when count(*) >= 5
        then 'PASS'
        else 'FAIL'
    end as m5_backtest_metric_snapshot_acceptance,
    run_id,
    count(*) as metric_count
from ops_run_metric_snapshot
where metric_namespace = 'backtest'
group by run_id
order by run_id desc
limit 1;

-- 17. Latest backtest execution plan artifact
select
    id,
    run_id,
    artifact_type,
    artifact_code,
    artifact_name,
    storage_backend,
    uri,
    mime_type,
    file_size_bytes,
    artifact_metadata,
    created_at
from ops_run_artifact
where artifact_code = 'backtest_execution_plan_json'
order by id desc
limit 5;


-- 18. M5.6 execution plan metric snapshot
select
    run_id,
    metric_namespace,
    metric_code,
    metric_value_numeric,
    metric_value_text,
    dimension_type,
    dimension_key,
    sequence_no,
    created_at
from ops_run_metric_snapshot
where metric_namespace = 'backtest'
  and run_id = 61
order by sequence_no asc;


-- 19. M5.6 execution plan artifact acceptance
select
    case
        when artifact_code = 'backtest_execution_plan_json'
         and artifact_type = 'JSON'
         and storage_backend = 'LOCAL'
         and uri like '%backtest_execution_plan_run_61.json'
        then 'PASS'
        else 'FAIL'
    end as m5_backtest_execution_plan_artifact_acceptance,
    id as artifact_id,
    run_id,
    artifact_code,
    artifact_type,
    storage_backend,
    uri,
    file_size_bytes
from ops_run_artifact
where run_id = 61
  and artifact_code = 'backtest_execution_plan_json'
order by id desc
limit 1;


-- 20. M5.6 execution plan metric acceptance
select
    case
        when max(case when metric_code = 'signal_selected_count' then metric_value_numeric end) = 30
         and max(case when metric_code = 'signal_instrument_count' then metric_value_numeric end) = 30
         and max(case when metric_code = 'data_bar_rows' then metric_value_numeric end) = 5520
         and max(case when metric_code = 'data_trade_day_count' then metric_value_numeric end) = 184
         and max(case when metric_code = 'data_covered_instrument_count' then metric_value_numeric end) = 30
        then 'PASS'
        else 'FAIL'
    end as m5_backtest_execution_plan_metric_acceptance,
    run_id,
    max(case when metric_code = 'signal_selected_count' then metric_value_numeric end) as signal_selected_count,
    max(case when metric_code = 'signal_instrument_count' then metric_value_numeric end) as signal_instrument_count,
    max(case when metric_code = 'data_bar_rows' then metric_value_numeric end) as data_bar_rows,
    max(case when metric_code = 'data_trade_day_count' then metric_value_numeric end) as data_trade_day_count,
    max(case when metric_code = 'data_covered_instrument_count' then metric_value_numeric end) as data_covered_instrument_count
from ops_run_metric_snapshot
where metric_namespace = 'backtest'
  and run_id = 61
group by run_id;

-- 21. M5.8 latest real backtrader result
select
    id,
    run_id,
    backtest_request_id,
    result_status,
    start_date,
    end_date,
    trading_days,
    initial_cash,
    final_equity,
    total_return,
    annual_return,
    benchmark_return,
    excess_return,
    max_drawdown,
    sharpe_ratio,
    volatility,
    order_count,
    trade_count,
    result_summary,
    completed_at
from research_backtest_result
where run_id = 61
order by id desc
limit 1;


-- 22. M5.8 real backtrader metric snapshot
select
    run_id,
    metric_namespace,
    metric_code,
    metric_value_numeric,
    metric_value_text,
    dimension_type,
    dimension_key,
    sequence_no,
    created_at
from ops_run_metric_snapshot
where run_id = 61
  and metric_namespace = 'backtest'
order by sequence_no asc;


-- 23. M5.8 real backtrader series count
select
    run_id,
    series_namespace,
    series_code,
    count(*) as row_count,
    min(trade_date) as min_trade_date,
    max(trade_date) as max_trade_date
from ops_run_series_snapshot
where run_id = 61
  and series_namespace = 'backtest'
group by run_id, series_namespace, series_code
order by series_code;


-- 24. M5.8 real backtrader artifacts
select
    id,
    run_id,
    artifact_code,
    artifact_type,
    storage_backend,
    uri,
    mime_type,
    file_size_bytes,
    artifact_metadata,
    created_at
from ops_run_artifact
where run_id = 61
  and artifact_code in (
      'backtest_metrics_json',
      'backtest_equity_curve_csv',
      'backtest_trade_log_csv'
  )
order by artifact_code;


-- 25. M5.8 real backtrader acceptance
select
    case
        when result_status = 'SUCCESS'
         and initial_cash = 10000000.000000
         and final_equity = 9749133.62932400
         and round(total_return, 8) = -0.02508664
         and round(annual_return, 8) = -0.03419767
         and round(max_drawdown, 8) = -0.25480463
         and round(sharpe_ratio, 8) = -0.06033385
         and round(volatility, 8) = 0.25128005
         and order_count = 90
         and trade_count = 30
         and trading_days = 184
        then 'PASS'
        else 'FAIL'
    end as m5_real_backtrader_acceptance,
    run_id,
    backtest_request_id,
    result_status,
    initial_cash,
    final_equity,
    round(total_return, 8) as total_return,
    round(annual_return, 8) as annual_return,
    round(max_drawdown, 8) as max_drawdown,
    round(sharpe_ratio, 8) as sharpe_ratio,
    round(volatility, 8) as volatility,
    order_count,
    trade_count,
    trading_days
from research_backtest_result
where run_id = 61
  and backtest_request_id = 2;


-- 26. M5.8 series acceptance
select
    case
        when count(*) = 736
        then 'PASS'
        else 'FAIL'
    end as m5_real_backtrader_series_acceptance,
    count(*) as series_rows
from ops_run_series_snapshot
where run_id = 61
  and series_namespace = 'backtest';


-- 27. M5.8 artifact acceptance
select
    case
        when count(*) = 3
        then 'PASS'
        else 'FAIL'
    end as m5_real_backtrader_artifact_acceptance,
    count(*) as artifact_count
from ops_run_artifact
where run_id = 61
  and artifact_code in (
      'backtest_metrics_json',
      'backtest_equity_curve_csv',
      'backtest_trade_log_csv'
  );

-- 28. M5.9 trade log status distribution
-- order_count = Submitted + Accepted + Completed notifications
-- trade_count = Completed only
select
    'Manual artifact check required for CSV distribution' as note,
    run_id,
    artifact_code,
    uri
from ops_run_artifact
where run_id = 61
  and artifact_code = 'backtest_trade_log_csv';


-- 29. M5.9 result / metric consistency
select
    case
        when r.result_status = 'SUCCESS'
         and r.order_count = max(case when m.metric_code = 'order_count' then m.metric_value_numeric end)
         and r.trade_count = max(case when m.metric_code = 'trade_count' then m.metric_value_numeric end)
         and r.trading_days = max(case when m.metric_code = 'trading_days' then m.metric_value_numeric end)
         and round(r.final_equity, 8) = round(max(case when m.metric_code = 'final_equity' then m.metric_value_numeric end), 8)
         and round(r.total_return, 8) = round(max(case when m.metric_code = 'total_return' then m.metric_value_numeric end), 8)
        then 'PASS'
        else 'FAIL'
    end as m5_result_metric_consistency,
    r.run_id,
    r.order_count,
    r.trade_count,
    r.trading_days,
    r.final_equity,
    r.total_return
from research_backtest_result r
join ops_run_metric_snapshot m
  on r.run_id = m.run_id
 and m.metric_namespace = 'backtest'
where r.run_id = 61
group by
    r.run_id,
    r.result_status,
    r.order_count,
    r.trade_count,
    r.trading_days,
    r.final_equity,
    r.total_return;


-- 30. M5.9 series completeness
select
    case
        when count(*) = 4
         and min(row_count) = 184
         and max(row_count) = 184
        then 'PASS'
        else 'FAIL'
    end as m5_series_completeness,
    count(*) as series_code_count,
    min(row_count) as min_rows_per_series,
    max(row_count) as max_rows_per_series,
    sum(row_count) as total_series_rows
from (
    select
        series_code,
        count(*) as row_count
    from ops_run_series_snapshot
    where run_id = 61
      and series_namespace = 'backtest'
      and series_code in (
          'portfolio_equity',
          'cash',
          'holding_count',
          'gross_exposure'
      )
    group by series_code
) s;


-- 31. M5.9 holding count sanity
select
    case
        when max(value_numeric) > 0
        then 'PASS'
        else 'FAIL'
    end as m5_holding_count_sanity,
    min(value_numeric) as min_holding_count,
    max(value_numeric) as max_holding_count
from ops_run_series_snapshot
where run_id = 61
  and series_namespace = 'backtest'
  and series_code = 'holding_count';


-- 32. M5.9 artifact file metadata
select
    case
        when count(*) = 3
         and min(file_size_bytes) > 0
        then 'PASS'
        else 'FAIL'
    end as m5_artifact_metadata_sanity,
    count(*) as artifact_count,
    min(file_size_bytes) as min_file_size,
    max(file_size_bytes) as max_file_size
from ops_run_artifact
where run_id = 61
  and artifact_code in (
      'backtest_metrics_json',
      'backtest_equity_curve_csv',
      'backtest_trade_log_csv'
  );

-- 35. M5.11 strict NEXT_OPEN acceptance
select
    case
        when result_status = 'SUCCESS'
         and result_summary ->> 'stage' = 'M5.11_STRICT_NEXT_OPEN_MINIMAL_EXECUTION'
         and result_summary ->> 'strict_next_open' = 'true'
         and result_summary ->> 'next_fallback_used' = 'false'
         and result_summary ->> 'preload_start_date' = '2024-03-29'
         and result_summary -> 'rebalance_records' -> 0 ->> 'source' = 'nextstart_open'
         and order_count = 90
         and trade_count = 30
         and trading_days = 184
        then 'PASS'
        else 'FAIL'
    end as m5_strict_next_open_acceptance,
    run_id,
    backtest_request_id,
    result_status,
    result_summary ->> 'stage' as stage,
    result_summary ->> 'strict_next_open' as strict_next_open,
    result_summary ->> 'next_fallback_used' as next_fallback_used,
    result_summary ->> 'preload_start_date' as preload_start_date,
    result_summary -> 'rebalance_records' -> 0 ->> 'source' as rebalance_source,
    order_count,
    trade_count,
    trading_days
from research_backtest_result
where run_id = 61
  and backtest_request_id = 2;


-- 36. M5.11 rebalance log artifact acceptance
select
    case
        when artifact_code = 'backtest_rebalance_log_csv'
         and artifact_type = 'CSV'
         and storage_backend = 'LOCAL'
         and file_size_bytes > 0
        then 'PASS'
        else 'FAIL'
    end as m5_rebalance_log_artifact_acceptance,
    id,
    run_id,
    artifact_code,
    artifact_type,
    storage_backend,
    uri,
    file_size_bytes,
    artifact_metadata
from ops_run_artifact
where run_id = 61
  and artifact_code = 'backtest_rebalance_log_csv';
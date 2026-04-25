-- stock_quant_v2｜M6 Paper Trading 最小闭环验收 SQL
-- 最新一键总编排验收结果：
-- target_run_id = 111
-- order_run_id = 112
-- fill_run_id = 113
-- position_snapshot_run_id = 114
-- ledger_run_id = 115
-- portfolio_id = 1
-- source_signal_run_id = 81
-- source_screen_request_id = 3
-- as_of_date = 2026-04-17
-- effective_date = 2026-04-20

-- 1. paper account
select
    id,
    account_code,
    account_name,
    account_type,
    market_code,
    base_currency,
    initial_cash,
    status
from trading_paper_account
where account_code = 'paper_cn_a_default'
order by id;

-- 2. paper portfolio
select
    id,
    account_id,
    portfolio_code,
    portfolio_name,
    strategy_version_id,
    execution_assumption_profile_id,
    source_signal_run_id,
    source_screen_request_id,
    portfolio_construction_mode,
    rebalance_frequency,
    max_position_count,
    long_only,
    initial_cash,
    start_date,
    status
from trading_paper_portfolio
where id = 1;

-- 3. source strategy signal
select
    run_id,
    count(*) as signal_count,
    min(as_of_date) as min_as_of_date,
    max(as_of_date) as max_as_of_date,
    min(effective_date) as min_effective_date,
    max(effective_date) as max_effective_date,
    min(reason_code) as min_reason_code,
    max(reason_code) as max_reason_code
from strategy_signal
where run_id = 81
group by run_id;

-- 4. target position summary
select
    run_id,
    portfolio_id,
    source_signal_run_id,
    source_screen_request_id,
    as_of_date,
    effective_date,
    count(*) as target_count,
    min(target_weight) as min_target_weight,
    max(target_weight) as max_target_weight,
    sum(target_weight) as sum_target_weight,
    min(rank_no) as min_rank_no,
    max(rank_no) as max_rank_no,
    status,
    count(*) as status_count
from trading_paper_target_position
where run_id = 111
  and portfolio_id = 1
group by
    run_id,
    portfolio_id,
    source_signal_run_id,
    source_screen_request_id,
    as_of_date,
    effective_date,
    status
order by status;

-- 5. paper order summary
select
    run_id,
    portfolio_id,
    effective_date,
    count(*) as order_count,
    min(order_quantity) as min_order_quantity,
    max(order_quantity) as max_order_quantity,
    sum(estimated_gross_amount) as total_estimated_gross_amount,
    sum(estimated_fee) as total_estimated_fee,
    sum(estimated_net_amount) as total_estimated_net_amount,
    status,
    count(*) as status_count
from trading_paper_order
where run_id = 112
  and portfolio_id = 1
group by
    run_id,
    portfolio_id,
    effective_date,
    status
order by status;

-- 6. paper fill summary
select
    run_id,
    portfolio_id,
    fill_date,
    count(*) as fill_count,
    min(fill_quantity) as min_fill_quantity,
    max(fill_quantity) as max_fill_quantity,
    sum(gross_amount) as total_gross_amount,
    sum(commission_amount) as total_commission_amount,
    sum(stamp_duty_amount) as total_stamp_duty_amount,
    sum(transfer_fee_amount) as total_transfer_fee_amount,
    sum(slippage_amount) as total_slippage_amount,
    sum(total_fee_amount) as total_fee_amount,
    sum(net_amount) as total_net_amount,
    sum(cash_delta) as total_cash_delta,
    fill_status,
    count(*) as status_count
from trading_paper_fill
where run_id = 113
  and portfolio_id = 1
group by
    run_id,
    portfolio_id,
    fill_date,
    fill_status
order by fill_status;

-- 7. paper position summary
select
    run_id,
    portfolio_id,
    position_date,
    count(*) as position_count,
    min(quantity) as min_quantity,
    max(quantity) as max_quantity,
    sum(quantity) as total_quantity,
    sum(cost_amount) as total_cost_amount,
    sum(market_value) as total_market_value,
    sum(unrealized_pnl) as total_unrealized_pnl,
    position_status,
    count(*) as status_count
from trading_paper_position
where run_id = 114
  and portfolio_id = 1
group by
    run_id,
    portfolio_id,
    position_date,
    position_status
order by position_status;

-- 8. portfolio snapshot
select
    id,
    run_id,
    portfolio_id,
    snapshot_date,
    cash_balance,
    market_value,
    total_equity,
    cash_balance + market_value as expected_total_equity,
    total_equity - (cash_balance + market_value) as equity_diff,
    gross_exposure,
    net_exposure,
    holding_count,
    daily_pnl,
    cumulative_pnl,
    daily_return,
    cumulative_return,
    turnover_amount,
    turnover_rate
from trading_paper_portfolio_snapshot
where run_id = 114
  and portfolio_id = 1;

-- 9. cash formula
select
    s.run_id,
    s.portfolio_id,
    p.initial_cash,
    f.total_cash_delta,
    s.cash_balance,
    p.initial_cash + f.total_cash_delta as expected_cash_balance,
    s.cash_balance - (p.initial_cash + f.total_cash_delta) as cash_diff
from trading_paper_portfolio_snapshot s
join trading_paper_portfolio p
    on p.id = s.portfolio_id
join (
    select
        portfolio_id,
        sum(cash_delta) as total_cash_delta
    from trading_paper_fill
    where run_id = 113
      and fill_status = 'COMPLETED'
    group by portfolio_id
) f
    on f.portfolio_id = s.portfolio_id
where s.run_id = 114
  and s.portfolio_id = 1;

-- 10. trade ledger summary
select
    run_id,
    portfolio_id,
    event_type,
    count(*) as event_count
from trading_paper_trade_ledger
where run_id = 115
  and portfolio_id = 1
group by
    run_id,
    portfolio_id,
    event_type
order by event_type;

-- 11. metric snapshot
select
    run_id,
    metric_namespace,
    count(*) as metric_count
from ops_run_metric_snapshot
where run_id = 114
group by run_id, metric_namespace
order by metric_namespace;

select
    metric_namespace,
    metric_code,
    metric_value_numeric,
    metric_value_text
from ops_run_metric_snapshot
where run_id = 114
  and metric_namespace = 'M6_PAPER_TRADING'
order by metric_code;

-- 12. series snapshot
select
    run_id,
    series_namespace,
    count(*) as series_count
from ops_run_series_snapshot
where run_id = 114
group by run_id, series_namespace
order by series_namespace;

select
    series_namespace,
    series_code,
    value_numeric
from ops_run_series_snapshot
where run_id = 114
  and series_namespace = 'M6_PAPER_TRADING'
order by series_code;

-- 13. ops_run chain
select
    id,
    run_type,
    run_name,
    status,
    context_json,
    started_at,
    ended_at
from ops_run
where id in (111, 112, 113, 114, 115)
order by id;
-- M7.7 price gap diagnosis for the real core_daily_bar schema.
-- Usage in Python is recommended if psql is unavailable.
-- Variables:
--   target_position_run_id
--   portfolio_id
--   effective_date

select
    t.instrument_id,
    t.target_quantity,
    b.open,
    b.close,
    b.trade_date
from trading_paper_target_position t
left join core_daily_bar b
  on b.instrument_id = t.instrument_id
 and b.trade_date = :effective_date
 and coalesce(b.price_adjust_type, 'RAW') = 'RAW'
where t.run_id = :target_position_run_id
  and t.portfolio_id = :portfolio_id
  and t.target_quantity > 0
  and b.instrument_id is null
order by t.instrument_id;

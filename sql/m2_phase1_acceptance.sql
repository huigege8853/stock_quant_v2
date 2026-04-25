-- 1. daily_bar RAW 當日總數
select count(*) as daily_bar_raw_count
from core_daily_bar
where trade_date = date '2024-01-02'
  and price_adjust_type = 'RAW';

-- 2. daily_bar 按交易所分布
select e.exchange_code, count(*) as row_count
from core_daily_bar b
join meta_instrument i on i.id = b.instrument_id
join meta_exchange e on e.id = i.exchange_id
where b.trade_date = date '2024-01-02'
  and b.price_adjust_type = 'RAW'
group by e.exchange_code
order by e.exchange_code;

-- 3. adjust_factor 當日總數
select count(*) as adjust_factor_count
from core_adjust_factor
where trade_date = date '2024-01-02';

-- 4. market_breadth 當日快照
select *
from core_market_breadth
where trade_date = date '2024-01-02'
order by market_scope;

-- 5. instrument 類型分布
select instrument_type, count(*) as row_count
from meta_instrument
group by instrument_type
order by instrument_type;

-- 6. 股票 universe 按交易所分布
select e.exchange_code, count(*) as stock_universe_count
from meta_instrument i
join meta_exchange e on e.id = i.exchange_id
where i.is_active = true
  and (
    (e.exchange_code = 'SSE' and i.symbol like any(array['600%','601%','603%','605%','688%','689%']))
    or
    (e.exchange_code = 'SZSE' and i.symbol like any(array['000%','001%','002%','003%','300%','301%']))
    or
    (e.exchange_code = 'BSE' and i.symbol like any(array['430%','830%','831%','832%','833%','835%','836%','837%','838%','839%']))
  )
group by e.exchange_code
order by e.exchange_code;
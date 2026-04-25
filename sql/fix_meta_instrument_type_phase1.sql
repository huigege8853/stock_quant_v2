-- 將明顯指數類從 EQUITY 糾偏為 INDEX
update meta_instrument i
set instrument_type = 'INDEX',
    updated_at = now()
from meta_exchange e
where e.id = i.exchange_id
  and i.instrument_type = 'EQUITY'
  and (
    i.display_name like '%指数%'
    or i.display_name like '%综指%'
    or i.display_name like '%沪深300%'
    or i.display_name like '%中证%'
    or i.display_name like '%上证50%'
    or i.display_name like '%上证180%'
    or i.display_name like '%上证380%'
    or i.display_name like '%等权%'
    or i.display_name like '%成长%'
    or i.display_name like '%价值%'
    or i.display_name like '%红利%'
    or i.display_name like '%主题%'
    or i.display_name like '%波动%'
    or i.display_name like '%行业%'
    or i.display_name like '%龙头%'
    or i.display_name like '%全指%'
    or i.display_name like '%中盘%'
    or i.display_name like '%小盘%'
  );

-- 將明顯債券指數類從 EQUITY 糾偏為 BOND_INDEX
update meta_instrument i
set instrument_type = 'BOND_INDEX',
    updated_at = now()
from meta_exchange e
where e.id = i.exchange_id
  and i.instrument_type = 'EQUITY'
  and (
    i.display_name like '%债%'
    or i.display_name like '%国债%'
    or i.display_name like '%企债%'
    or i.display_name like '%信用债%'
    or i.display_name like '%可转换债券%'
  );

-- 將明顯基金類從 EQUITY 糾偏為 FUND_INDEX
update meta_instrument i
set instrument_type = 'FUND_INDEX',
    updated_at = now()
from meta_exchange e
where e.id = i.exchange_id
  and i.instrument_type = 'EQUITY'
  and i.display_name like '%基金%';
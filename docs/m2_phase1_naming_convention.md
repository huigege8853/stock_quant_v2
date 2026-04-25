# M2 命名規則

## 1. 規則
所有資料庫對象名盡量控制在 30 字符內。

## 2. 前綴
- uq_: 唯一約束
- ix_: 索引
- fk_: 外鍵

## 3. 縮寫建議
- daily_bar -> dbar
- adjust_factor -> adjfac
- market_breadth -> mbrdth

## 4. 例子
- uq_stg_dbar_key
- uq_stg_adjfac_key
- uq_core_mbrdth_key
- ix_daily_bar_trade_date

## 5. repository 規則
repository 中 `constraint="..."` 必須與 migration/實際庫中的約束名完全一致，禁止手寫猜測。
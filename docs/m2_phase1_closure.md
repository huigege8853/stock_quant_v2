# M2 第一階段收尾說明

## 1. 範圍
本階段完成以下主題的主鏈收斂：
- Instrument
- TradingCalendar
- DailyBar
- AdjustFactor
- MarketBreadth

## 2. 當前主鏈順序
Instrument -> TradingCalendar -> DailyBar -> AdjustFactor -> MarketBreadth

## 3. 股票 universe 規則
股票 universe 統一通過 `load_cn_stock_universe()` 生成：
- SSE: 600/601/603/605/688/689
- SZSE: 000/001/002/003/300/301
- BSE: 430/830/831/832/833/835/836/837/838/839

## 4. instrument 類型規則
canonical instrument_type:
- EQUITY
- INDEX
- BOND_INDEX
- FUND_INDEX
- UNKNOWN

未知對象不再默認寫為 EQUITY。

## 5. provider/fallback 狀態
### DailyBar
- 主命中 provider: baostock
- fallback 順序已保留：baostock, sina, akshare, pytdx, tushare, paid, skip

### AdjustFactor
- 主命中 provider: baostock
- provider 返回變更點，平台層轉為目標交易日快照

### MarketBreadth
- derived 主題
- universe_source = load_cn_stock_universe
- 依附 daily_bar 數據版本

## 6. 已修復問題
- stg_daily_bar 誤用 adjust_factor staging 約束名
- instrument 中大量指數類被錯分為 EQUITY
- daily_bar 與 market_breadth universe 口徑不一致
- checkpoint_json 中不可序列化對象導致 flush 失敗
- CoreDailyBar 字段名適配問題

## 7. 已知技術債
- provider builder 可選依賴仍需統一封裝
- repository 層缺少最小單測
- 命名規則尚未整理成獨立文檔
- bootstrap 仍屬 phase-1 專用入口，後續需抽象成通用 orchestration

## 8. 第二階段前置條件
- 以 phase-1 acceptance SQL 作為基線
- 以 phase-1 closure 文檔作為口徑依據
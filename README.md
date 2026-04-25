stock_quant_v2_M2_1 :  first daily_bar pipeline end-to-end working with baostock(一版 daily_bar 数据流水线已经能从头到尾接通，并且使用的是 baostock———— 20260404

stock_quant_v2_M2_2: M2_2 行情域稳定化阶段已完成,收斂已完成

项目名称：stock_quant_v2
当前阶段：M2 已完成，进入 M3
当前状态：
- M1 已完成
- M2_1 已完成
- M2_2 已完成
- M2 剩余主题已完成收口

已完成：
- instrument
- trading_calendar
- daily_bar
- adjust_factor
- market_breadth
- market_index_bar
- price_limit_daily V1
- instrument_status_daily V1
- tag V1
- instrument_tag V1

已完成但暂不稳定：
- FundamentalSnapshot 已完成工程骨架，但当前免费 provider 不稳定，运行口径按 SKIPPED + WARN 收口，不作为 M3 阻塞项

M2 收尾遗留项：
1. 清理历史 stale RUNNING 记录
2. bootstrap_instrument_calendar.py 当前不可作为正式主流程脚本（date JSON 序列化问题）
3. daily_bar 历史全量回填能力仍有旧 SQL 问题（calendar_date 字段）
4. market_breadth / market_index_bar 当前还不是完整历史覆盖
5. adjust_factor 当前并非全 universe 全覆盖

M3 建议优先依赖的数据底座：
- meta_instrument
- meta_trading_calendar
- core_daily_bar
- core_adjust_factor
- core_price_limit_daily
- core_instrument_status_daily
- tag
- instrument_tag

请基于此状态直接开始 M3 设计与落地，不要回退到已完成的 M2 主链和已解决问题。

M3 指标/特征域，并已完成 M3 的四层首链验收
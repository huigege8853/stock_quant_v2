# M4 ｜ 07_next_chat_brief

项目名称：stock_quant_v2

当前阶段：M4 策略域  
当前状态：

- M1 已完成
- M2 主链已完成，严格模式 daily_bar 历史回填主链已跑通
- M3 已完成 indicator / factor / feature / label 四层首链验收
- M4 最小可用规则策略主链已跑通

当前 M4 已确认通过：

1. strategy core 已落地：
   - `strategy_definition`
   - `strategy_version`
   - `strategy_parameter_schema`
   - `strategy_signal`

2. 首条规则策略主链已跑通：
   - strategy: `alpha_selection`
   - version: `v1`
   - feature set: `fs_daily_alpha_v1:v1`

3. 首轮成功运行结果：
   - `as_of_date = 2024-03-29`
   - `effective_date = 2024-04-01`
   - `selected_count = 30`
   - `eligible_universe_size = 5027`
   - `score_min = 0.78414561`
   - `score_max = 0.84932365`
   - `score_avg = 0.8006165`

4. 当前锁定结论：
   - Signal 只表达研究判断，不表达仓位
   - `strategy_signal.run_id` 强绑定 `ops_run.id`
   - `strategy_signal.instrument_id` 绑定 `meta_instrument.id`，但允许为空以兼容 market / portfolio signal
   - `effective_date` 由 `meta_trading_calendar` 推导下一交易日
   - 当前 bootstrap 脚本已开始收薄，领域逻辑下沉到 `strategy_domain`
   - `tradable_flag` 当前不阻塞 M4 首链，但其最终语义仍需锁定

当前未完成但应继续推进的优先项：

1. 锁定 `feat_tradable_flag` 语义
2. 补最小单元测试：
   - 参数校验
   - 规则打分 / top_n / 排序
3. 补 timing 策略骨架：
   - `subject_type = market`
   - `subject_key = market:CN_A`
4. 为 M5 screen / backtest 准备 strategy → signal 接口

请基于以上状态，直接继续推进下一步，优先输出：

- M4 最小测试集
- timing strategy 骨架
- M5 screen / backtest 对 strategy_signal 的消费契约
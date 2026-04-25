
---

# 9. `docs/modules/m6/08_open_items.md`

```md
# M6 Open Items

M6 最小闭环已完成，以下开放项不阻塞 M6 验收。

## 1. 多日持仓滚动

当前 M6 只完成单日：

```text
2026-04-17 signal
2026-04-20 execution

后续需要支持：

D 日 snapshot
D+1 日 position carry forward
D+1 日 available_quantity 更新

建议放入 M7。

2. T+1 可卖数量更新

当前买入当日：

available_quantity = 0

后续需要在下一交易日更新：

available_quantity = quantity

建议放入 M7。

3. 调仓卖出

当前 M6 首链只有 BUY。

后续需要支持：

目标持仓下降
目标剔除
SELL order
SELL fill
realized_pnl
stamp_duty

建议放入 M7。

4. 风控约束

当前只做：

STRICT_CASH
lot_size
NEXT_OPEN
basic fee/slippage

后续可扩展：

单票最大权重
行业约束
停牌过滤
涨跌停约束
最大换手率
最大回撤保护

建议放入 M7 / M8。

5. 多策略 / 多组合

当前 M6 是单策略、单组合、单账户。

后续可扩展：

multi strategy
multi portfolio
portfolio group
capital allocation
6. 更完整的 ledger event

当前 ledger 为最小审计流水。

后续可增加：

ORDER_CREATED
ORDER_REJECTED
CASH_CHANGED
RISK_CHECKED
REBALANCE_STARTED
REBALANCE_FINISHED
7. M6 文档进一步自动化

当前 docs 已手工固化。

后续可以增加：

自动生成 acceptance report
自动导出 JSON / Markdown run report

---


# M7-Risk Open Items

M7-Risk 最小闭环已通过，本文件记录不阻塞当前验收的后续增强项。

## 1. 行业暴露约束

目标：

```text
单行业最大权重
单行业最大持仓数
行业黑名单 / 白名单
```

需要依赖：

```text
instrument_tag
tag
industry classification
```

建议规则码：

```text
R007_INDUSTRY_MAX_WEIGHT
R008_INDUSTRY_MAX_COUNT
```

## 2. 市场风险开关

目标：

```text
市场整体风险开关
大盘跌破阈值时降低总仓位
指数波动率过高时降低总仓位
极端行情时禁止新增 BUY
```

建议规则码：

```text
R009_MARKET_RISK_SWITCH
R010_PORTFOLIO_GROSS_EXPOSURE_CAP
```

## 3. 流动性约束

目标：

```text
日成交额过滤
目标成交额不超过 ADV 百分比
低流动性标的拒绝或降权
```

建议规则码：

```text
R011_MIN_LIQUIDITY_FILTER
R012_ADV_PARTICIPATION_CAP
```

## 4. 最大换手率

目标：

```text
单日组合换手率上限
单票换手率上限
超限时按比例缩放
```

建议规则码：

```text
R013_PORTFOLIO_TURNOVER_CAP
R014_SINGLE_NAME_TURNOVER_CAP
```

## 5. ST / 特殊状态过滤

当前已支持：

```text
core_instrument_status_daily.is_suspended
```

可继续增强：

```text
is_st
退市整理
风险警示
长期停牌
上市不足 N 日
```

建议规则码：

```text
R015_ST_FILTER
R016_LISTING_AGE_FILTER
```

## 6. 风控可观测性

后续建议：

```text
risk_decision export
risk profile diff report
risk adjusted target report
risk contribution report
run metric snapshot
```

M8 可接入：

```text
m8_query_risk_decision
m8_export_risk_report
```

## 7. 数据完备性

当前 M7-Risk 已暴露数据缺口：

```text
R003_MISSING_STATUS
R004_MISSING_PRICE_LIMIT
R005_MISSING_EFFECTIVE_PRICE
```

后续 M2/M8 应补：

```text
target universe data readiness check
effective date open completeness
instrument status completeness
price limit completeness
```

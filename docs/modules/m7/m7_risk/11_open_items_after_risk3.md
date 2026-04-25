# M7-Risk Open Items After Risk3

M7 风控域已通过，本文件记录后续增强项。

## 1. 行业数据接入

当前状态：

```text
industry_coverage_count = 0
industry_missing_count = 30
```

后续建议：

```text
补充 industry tag 数据
统一 tag / instrument_tag 行业分类规范
支持申万一级 / 二级行业
支持中信行业或自定义行业
```

## 2. 市场风险开关自动化

当前 R009 支持 profile 参数：

```text
NORMAL
REDUCE
NO_BUY
LIQUIDATE
```

后续建议接入：

```text
market_index
指数趋势
指数波动率
市场宽度
大盘跌破阈值
```

## 3. 流动性约束增强

当前 R011 支持：

```text
min_turnover_amount
max_participation_rate
```

后续建议：

```text
ADV 5日 / 20日
成交额分位数
停牌前流动性衰减
单票成交金额上限
组合成交金额上限
```

## 4. 风控报告

M8 建议支持：

```text
risk decision summary
profile compare report
risk adjusted target diff
risk reject list
risk warning list
risk adjustment attribution
```

## 5. 与调度系统集成

M8/M9 后续可以将风控链路纳入每日调度：

```text
target sizing
risk apply
risk quality check
rebalance
snapshot
report export
```

# M7-Risk.3 Scope

M7-Risk.3 covers three additional risk categories:

```text
R007_INDUSTRY_MAX_WEIGHT
R009_MARKET_RISK_SWITCH
R011_LIQUIDITY_FILTER
```

## Design

M7-Risk.3 is implemented as an overlay on top of a source target run.

Recommended source:

```text
source_target_run_id = 160
```

This means:

```text
M7.7 original target run = 155
M7-Risk.1/2 adjusted target run = 160
M7-Risk.3 overlay adjusted target run = new run id
```

The source target run is never mutated.

## Profiles

```text
paper_cn_a_risk3_observe_v1
paper_cn_a_risk3_conservative_v1
paper_cn_a_risk3_strict_v1
```

## Acceptance

M7-Risk.3 passes when:

```text
risk_decision rows exist
R007/R009/R011 reason codes exist
WARN / ADJUST / REJECT exists
adjusted target run exists
```

# M7-Risk.2 Profile Variants

M7-Risk.2 validates that risk profiles are not just logs, but can materially change target positions.

## Profiles

| profile_code | purpose |
|---|---|
| paper_cn_a_default_risk_v1 | Default paper trading profile. Missing data is WARN. |
| paper_cn_a_conservative_risk_v1 | Max single position weight = 3%, expected to adjust targets. |
| paper_cn_a_data_strict_risk_v1 | Missing effective-date price = REJECT, expected to reject targets when data readiness fails. |

## Acceptance

Same source target run:

```text
source_target_run_id = 155
```

Different adjusted target runs:

```text
default adjusted_target_run_id = 160
conservative adjusted_target_run_id = 161
data strict adjusted_target_run_id = 162
```

Expected:

```text
same source target
different profile_code
different adjusted target quantity total
risk_decision records exist
REJECT or ADJUST decisions exist in at least one profile
```

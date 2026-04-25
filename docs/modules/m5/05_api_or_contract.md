
---

# 5. `docs/modules/m5/05_api_or_contract.md`

```markdown
# M5｜API / Contract

## 1. ScreenRequestDTO

```python
ScreenRequestDTO(
    strategy_code="alpha_selection",
    version_code="v1",
    as_of_date=date(2024, 3, 29),
    effective_date=date(2024, 4, 1),
    signal_lookup_mode="EXISTING_SIGNAL",
    source_signal_run_id=None,
    max_count=30,
    min_score=None,
    include_reason_codes=["TOP_N_SELECTED"],
    exclude_reason_codes=[],
    universe_filter={},
    signal_filter={},
    parameter_values={},
)
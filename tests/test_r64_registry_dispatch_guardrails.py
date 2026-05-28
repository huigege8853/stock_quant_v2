from stock_quant_v2.strategy_domain.services.multi_layer_regime_rotation_v2_registry_dispatch import (
    dispatch_r64_research_preview,
    get_r64_research_strategy_registry_entry,
)


def test_r64_registry_entry_is_research_only():
    entry = get_r64_research_strategy_registry_entry()
    assert entry["strategy_code"] == "multi_layer_regime_rotation_v2"
    assert entry["strategy_version_code"] == "v1_l0_l12_state_budget_theme_style"
    assert entry["formal_signal_allowed"] is False
    assert entry["trading_allowed"] is False
    assert entry["block_signal_generation"] is True
    assert entry["block_trading"] is True
    assert entry["gate_status"] == "OBSERVE_ONLY"
    assert entry["score"] == 0.0
    assert entry["weight_adjustment"] == 0.0
    assert entry["reason_code"] == "R64_REGISTRY_DISPATCH_RESEARCH_ONLY"
    assert entry["reason_text"]
    assert entry["evidence_json"]["source"] == "registry_entry"


def test_r64_dispatch_preview_blocks_signal_and_trade():
    payload = dispatch_r64_research_preview()
    assert payload["formal_signal_allowed"] is False
    assert payload["trading_allowed"] is False
    assert payload["block_signal_generation"] is True
    assert payload["block_trading"] is True
    assert payload["signal_rows"] == []
    assert payload["gate_status"] == "OBSERVE_ONLY"
    assert payload["score"] == 0.0
    assert payload["weight_adjustment"] == 0.0
    assert payload["reason_code"] == "R64_SIGNAL_BLOCKED_RESEARCH_ONLY"
    assert payload["reason_text"]
    assert payload["evidence_json"]["source"] == "signal_preview"

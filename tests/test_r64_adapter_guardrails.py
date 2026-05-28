from stock_quant_v2.strategy_domain.services.multi_layer_regime_rotation_v2_research_adapter import (
    MultiLayerRegimeRotationV2ResearchAdapter,
)


def test_r64_adapter_blocks_signal_and_trading():
    adapter = MultiLayerRegimeRotationV2ResearchAdapter()
    payload = adapter.build_signal_preview()
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
    assert payload["evidence_json"]["block_signal_generation"] is True

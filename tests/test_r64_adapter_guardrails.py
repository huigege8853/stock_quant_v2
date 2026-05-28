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

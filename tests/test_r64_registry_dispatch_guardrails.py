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
    assert entry["shadow_artifact_version"] == "r64_shadow_signal_artifact_v1"
    assert entry["backtest_request_dryrun_artifact_version"] == "r64_m5_backtest_request_dryrun_candidate_v1"
    assert entry["evidence_json"]["source"] == "registry_entry"
    assert entry["evidence_json"]["db_write_allowed"] is False


def test_r64_dispatch_preview_blocks_signal_and_trade():
    payload = dispatch_r64_research_preview()
    assert payload["formal_signal_allowed"] is False
    assert payload["trading_allowed"] is False
    assert payload["block_signal_generation"] is True
    assert payload["block_trading"] is True
    assert payload["signal_rows"] == []
    assert payload["shadow_candidate_rows"] == []
    assert payload["shadow_signal_rows"] == []
    assert payload["backtest_request_dryrun_candidate"]["artifact_type"] == "backtest_request_dryrun_candidate"
    assert payload["backtest_request_dryrun_candidate"]["artifact_version"] == "r64_m5_backtest_request_dryrun_candidate_v1"
    assert payload["backtest_request_dryrun_candidate"]["db_write_allowed"] is False
    assert payload["backtest_request_candidate"] == payload["backtest_request_dryrun_candidate"]
    assert payload["gate_status"] == "OBSERVE_ONLY"
    assert payload["score"] == 0.0
    assert payload["weight_adjustment"] == 0.0
    assert payload["reason_code"] == "R64_SIGNAL_BLOCKED_RESEARCH_ONLY"
    assert payload["reason_text"]
    assert payload["evidence_json"]["source"] == "signal_preview"


def test_r64_dispatch_preview_can_emit_shadow_artifact_only():
    payload = dispatch_r64_research_preview(
        decision_rows=[{"layer": "L7", "status": "preview"}],
        candidate_rows=[{"ts_code": "000001.SZ", "score": 1.0}],
    )
    assert payload["formal_signal_allowed"] is False
    assert payload["trading_allowed"] is False
    assert payload["signal_rows"] == []
    assert len(payload["shadow_candidate_rows"]) == 1
    assert len(payload["shadow_signal_rows"]) == 1
    assert payload["shadow_signal_rows"][0]["signal_status"] == "BLOCKED_RESEARCH_ONLY"
    assert payload["backtest_request_dryrun_candidate"]["request_status"] == "DRY_RUN_NOT_CREATED"
    assert payload["backtest_request_dryrun_candidate"]["create_mode"] == "DRY_RUN_ONLY"
    assert payload["backtest_request_dryrun_candidate"]["db_write_allowed"] is False
    assert payload["backtest_request_dryrun_candidate"]["backtest_request_created"] is False
    assert payload["backtest_request_dryrun_candidate"]["engine_payload"]["shadow_signal_row_count"] == 1
    assert payload["backtest_request_candidate"] == payload["backtest_request_dryrun_candidate"]
    assert payload["registry_entry"]["formal_signal_allowed"] is False

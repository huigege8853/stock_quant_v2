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
    assert payload["shadow_candidate_rows"] == []
    assert payload["shadow_signal_rows"] == []
    assert payload["backtest_request_dryrun_candidate"]["artifact_type"] == "backtest_request_dryrun_candidate"
    assert payload["backtest_request_dryrun_candidate"]["artifact_version"] == "r64_m5_backtest_request_dryrun_candidate_v1"
    assert payload["backtest_request_dryrun_candidate"]["create_mode"] == "DRY_RUN_ONLY"
    assert payload["backtest_request_dryrun_candidate"]["db_write_allowed"] is False
    assert payload["backtest_request_dryrun_candidate"]["backtest_request_created"] is False
    assert payload["backtest_request_candidate"] == payload["backtest_request_dryrun_candidate"]
    assert payload["strategy_compare_input_dryrun_candidate"]["artifact_type"] == "strategy_compare_input_dryrun_candidate"
    assert payload["strategy_compare_input_dryrun_candidate"]["artifact_version"] == "r64_strategy_compare_input_dryrun_candidate_v1"
    assert payload["strategy_compare_input_dryrun_candidate"]["compare_mode"] == "DRY_RUN_ONLY"
    assert payload["strategy_compare_input_dryrun_candidate"]["db_write_allowed"] is False
    assert payload["strategy_compare_input_dryrun_candidate"]["backtest_executed"] is False
    assert payload["strategy_compare_input_dryrun_candidate"]["strategy_compare_report_created"] is False
    assert payload["strategy_compare_input"] == payload["strategy_compare_input_dryrun_candidate"]
    assert payload["gate_status"] == "OBSERVE_ONLY"
    assert payload["score"] == 0.0
    assert payload["weight_adjustment"] == 0.0
    assert payload["reason_code"] == "R64_SIGNAL_BLOCKED_RESEARCH_ONLY"
    assert payload["reason_text"]
    assert payload["evidence_json"]["source"] == "signal_preview"
    assert payload["evidence_json"]["block_signal_generation"] is True


def test_r64_adapter_builds_shadow_artifact_without_formal_signal():
    adapter = MultiLayerRegimeRotationV2ResearchAdapter()
    payload = adapter.build_candidate_preview(
        decision_rows=[{"layer": "L7", "status": "preview"}],
        candidate_rows=[{"ts_code": "000001.SZ", "score": 1.23}],
    )
    assert payload["formal_signal_allowed"] is False
    assert payload["trading_allowed"] is False
    assert payload["block_signal_generation"] is True
    assert payload["block_trading"] is True
    assert payload["signal_rows"] == []
    assert payload["shadow_artifact_version"] == "r64_shadow_signal_artifact_v1"
    assert len(payload["shadow_candidate_rows"]) == 1
    assert len(payload["shadow_signal_rows"]) == 1
    assert payload["shadow_candidate_rows"][0]["ts_code"] == "000001.SZ"
    assert payload["shadow_signal_rows"][0]["signal_status"] == "BLOCKED_RESEARCH_ONLY"
    assert payload["shadow_signal_rows"][0]["target_weight"] == 0.0
    assert payload["backtest_request_dryrun_candidate"]["request_status"] == "DRY_RUN_NOT_CREATED"
    assert payload["backtest_request_dryrun_candidate"]["artifact_type"] == "backtest_request_dryrun_candidate"
    assert payload["backtest_request_dryrun_candidate"]["artifact_version"] == "r64_m5_backtest_request_dryrun_candidate_v1"
    assert payload["backtest_request_dryrun_candidate"]["create_mode"] == "DRY_RUN_ONLY"
    assert payload["backtest_request_dryrun_candidate"]["db_write_allowed"] is False
    assert payload["backtest_request_dryrun_candidate"]["backtest_request_created"] is False
    assert payload["backtest_request_dryrun_candidate"]["engine_payload"]["r64_shadow_only"] is True
    assert payload["backtest_request_dryrun_candidate"]["engine_payload"]["shadow_signal_row_count"] == 1
    assert payload["backtest_request_candidate"] == payload["backtest_request_dryrun_candidate"]
    assert payload["strategy_compare_input_dryrun_candidate"]["compare_status"] == "DRY_RUN_NOT_EXECUTED"
    assert payload["strategy_compare_input_dryrun_candidate"]["backtest_request_dryrun_candidate"] == payload["backtest_request_dryrun_candidate"]
    assert payload["strategy_compare_input_dryrun_candidate"]["strategy_compare_report_created"] is False
    assert payload["strategy_compare_input"] == payload["strategy_compare_input_dryrun_candidate"]
    assert payload["evidence_json"]["source"] == "candidate_preview"
    assert payload["evidence_json"]["shadow_signal_row_count"] == 1


def test_r64_adapter_builds_m5_compatible_backtest_request_dryrun_candidate():
    adapter = MultiLayerRegimeRotationV2ResearchAdapter()
    candidate = adapter.build_backtest_request_dryrun_candidate(shadow_signal_row_count=2)

    assert candidate["artifact_type"] == "backtest_request_dryrun_candidate"
    assert candidate["artifact_version"] == "r64_m5_backtest_request_dryrun_candidate_v1"
    assert candidate["request_status"] == "DRY_RUN_NOT_CREATED"
    assert candidate["create_mode"] == "DRY_RUN_ONLY"
    assert candidate["db_write_allowed"] is False
    assert candidate["backtest_request_created"] is False
    assert candidate["formal_signal_allowed"] is False
    assert candidate["trading_allowed"] is False
    assert candidate["block_signal_generation"] is True
    assert candidate["block_trading"] is True
    assert candidate["engine_code"] == "backtrader"
    assert candidate["engine_payload"]["shadow_signal_row_count"] == 2
    assert candidate["engine_payload"]["db_write_allowed"] is False
    assert candidate["evidence_json"]["source"] == "backtest_request_dryrun_candidate"


def test_r64_adapter_builds_strategy_compare_input_dryrun_candidate():
    adapter = MultiLayerRegimeRotationV2ResearchAdapter()
    candidate = adapter.build_strategy_compare_input_dryrun_candidate(shadow_signal_row_count=3)

    assert candidate["artifact_type"] == "strategy_compare_input_dryrun_candidate"
    assert candidate["artifact_version"] == "r64_strategy_compare_input_dryrun_candidate_v1"
    assert candidate["compare_status"] == "DRY_RUN_NOT_EXECUTED"
    assert candidate["compare_mode"] == "DRY_RUN_ONLY"
    assert candidate["db_write_allowed"] is False
    assert candidate["backtest_request_created"] is False
    assert candidate["backtest_executed"] is False
    assert candidate["strategy_compare_report_created"] is False
    assert candidate["formal_signal_allowed"] is False
    assert candidate["trading_allowed"] is False
    assert candidate["baseline_label"] == "current_production_baseline"
    assert "strategy_compare_report" in candidate["expected_reports"]
    assert "drawdown" in candidate["compare_dimensions"]
    assert candidate["backtest_request_dryrun_candidate"]["engine_payload"]["shadow_signal_row_count"] == 3
    assert candidate["evidence_json"]["source"] == "strategy_compare_input_dryrun_candidate"

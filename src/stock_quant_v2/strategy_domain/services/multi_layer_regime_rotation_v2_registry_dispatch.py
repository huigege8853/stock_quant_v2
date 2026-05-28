"""R64 research-only registry and dispatch bridge.

This module is inside the project source tree, but it is intentionally isolated
from existing production strategy core. It exposes a small registry/dispatch
entry for R64 preview only. It must not call M6/M7 production signal generation,
external_execution, live order, or production trading paths while guardrails are blocking.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional

from stock_quant_v2.strategy_domain.services.multi_layer_regime_rotation_v2_research_adapter import (
    MultiLayerRegimeRotationV2ResearchAdapter,
    R64AdapterConfig,
    R64_BACKTEST_REQUEST_DRYRUN_ARTIFACT_VERSION,
    R64_GATE_STATUS,
    R64_REASON_CODE,
    R64_REASON_TEXT,
    R64_SCORE,
    R64_SHADOW_ARTIFACT_VERSION,
    R64_STRATEGY_COMPARE_INPUT_DRYRUN_ARTIFACT_VERSION,
    R64_WEIGHT_ADJUSTMENT,
)


R64_STRATEGY_CODE = "multi_layer_regime_rotation_v2"
R64_STRATEGY_VERSION_CODE = "v1_l0_l12_state_budget_theme_style"


def get_r64_research_strategy_registry_entry() -> Dict[str, Any]:
    """Return a safe, research-only registry entry for R64."""
    return {
        "strategy_code": R64_STRATEGY_CODE,
        "strategy_version_code": R64_STRATEGY_VERSION_CODE,
        "strategy_family": "multi_layer_regime_rotation",
        "stage": "research_preview",
        "adapter_module": "stock_quant_v2.strategy_domain.services.multi_layer_regime_rotation_v2_research_adapter",
        "dispatch_module": __name__,
        "adapter_class": "MultiLayerRegimeRotationV2ResearchAdapter",
        "dispatch_function": "dispatch_r64_research_preview",
        "shadow_artifact_version": R64_SHADOW_ARTIFACT_VERSION,
        "backtest_request_dryrun_artifact_version": R64_BACKTEST_REQUEST_DRYRUN_ARTIFACT_VERSION,
        "strategy_compare_input_dryrun_artifact_version": R64_STRATEGY_COMPARE_INPUT_DRYRUN_ARTIFACT_VERSION,
        "formal_signal_allowed": False,
        "trading_allowed": False,
        "block_signal_generation": True,
        "block_trading": True,
        "gate_status": R64_GATE_STATUS,
        "score": R64_SCORE,
        "weight_adjustment": R64_WEIGHT_ADJUSTMENT,
        "reason_code": "R64_REGISTRY_DISPATCH_RESEARCH_ONLY",
        "reason_text": R64_REASON_TEXT,
        "evidence_json": {
            "source": "registry_entry",
            "strategy_code": R64_STRATEGY_CODE,
            "strategy_version_code": R64_STRATEGY_VERSION_CODE,
            "shadow_artifact_version": R64_SHADOW_ARTIFACT_VERSION,
            "strategy_compare_input_dryrun_artifact_version": R64_STRATEGY_COMPARE_INPUT_DRYRUN_ARTIFACT_VERSION,
            "formal_signal_allowed": False,
            "trading_allowed": False,
            "block_signal_generation": True,
            "block_trading": True,
            "db_write_allowed": False,
        },
    }


def build_r64_research_adapter(
    *,
    schema_name: str = "research_ops",
    full_decision_version: str = "r64_l0_l12_state_skeleton_v3",
    plan_version: str = "r64_prototype_candidate_plan_v1",
    backtest_version: str = "r64_research_prototype_backtest_dryrun_v1",
    shadow_artifact_version: str = R64_SHADOW_ARTIFACT_VERSION,
    top_n: int = 50,
) -> MultiLayerRegimeRotationV2ResearchAdapter:
    cfg = R64AdapterConfig(
        schema_name=schema_name,
        strategy_code=R64_STRATEGY_CODE,
        strategy_version_code=R64_STRATEGY_VERSION_CODE,
        full_decision_version=full_decision_version,
        plan_version=plan_version,
        backtest_version=backtest_version,
        shadow_artifact_version=shadow_artifact_version,
        top_n=top_n,
    )
    return MultiLayerRegimeRotationV2ResearchAdapter(cfg)


def dispatch_r64_research_preview(
    *,
    schema_name: str = "research_ops",
    full_decision_version: str = "r64_l0_l12_state_skeleton_v3",
    plan_version: str = "r64_prototype_candidate_plan_v1",
    backtest_version: str = "r64_research_prototype_backtest_dryrun_v1",
    shadow_artifact_version: str = R64_SHADOW_ARTIFACT_VERSION,
    top_n: int = 50,
    decision_rows: Optional[Iterable[Mapping[str, Any]]] = None,
    candidate_rows: Optional[Iterable[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build a blocked R64 research preview payload."""
    adapter = build_r64_research_adapter(
        schema_name=schema_name,
        full_decision_version=full_decision_version,
        plan_version=plan_version,
        backtest_version=backtest_version,
        shadow_artifact_version=shadow_artifact_version,
        top_n=top_n,
    )
    if decision_rows is None and candidate_rows is None:
        payload = adapter.build_signal_preview()
    else:
        payload = adapter.build_candidate_preview(
            decision_rows=decision_rows or [],
            candidate_rows=candidate_rows or [],
        )
        payload["signal_rows"] = []
    payload["registry_entry"] = get_r64_research_strategy_registry_entry()
    payload["formal_signal_allowed"] = False
    payload["trading_allowed"] = False
    payload["block_signal_generation"] = True
    payload["block_trading"] = True
    payload.setdefault("gate_status", R64_GATE_STATUS)
    payload.setdefault("score", R64_SCORE)
    payload.setdefault("weight_adjustment", R64_WEIGHT_ADJUSTMENT)
    payload.setdefault("reason_code", R64_REASON_CODE)
    payload.setdefault("reason_text", R64_REASON_TEXT)
    payload.setdefault("shadow_candidate_rows", [])
    payload.setdefault("shadow_signal_rows", [])
    payload.setdefault(
        "backtest_request_dryrun_candidate",
        adapter.build_backtest_request_dryrun_candidate(shadow_signal_row_count=0),
    )
    payload.setdefault("backtest_request_candidate", payload["backtest_request_dryrun_candidate"])
    payload.setdefault(
        "strategy_compare_input_dryrun_candidate",
        adapter.build_strategy_compare_input_dryrun_candidate(
            shadow_signal_row_count=len(payload.get("shadow_signal_rows", []))
        ),
    )
    payload.setdefault("strategy_compare_input", payload["strategy_compare_input_dryrun_candidate"])
    payload.setdefault(
        "evidence_json",
        {
            "source": "registry_dispatch",
            "strategy_code": R64_STRATEGY_CODE,
            "strategy_version_code": R64_STRATEGY_VERSION_CODE,
            "shadow_artifact_version": shadow_artifact_version,
            "backtest_request_dryrun_artifact_version": R64_BACKTEST_REQUEST_DRYRUN_ARTIFACT_VERSION,
            "strategy_compare_input_dryrun_artifact_version": R64_STRATEGY_COMPARE_INPUT_DRYRUN_ARTIFACT_VERSION,
            "formal_signal_allowed": False,
            "trading_allowed": False,
            "block_signal_generation": True,
            "block_trading": True,
            "db_write_allowed": False,
        },
    )
    return payload

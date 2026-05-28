"""Research-only adapter skeleton for R64 multi-layer regime rotation v2.

This module is intentionally conservative. It must not create formal strategy
signals or trading instructions until a later explicit release stage removes the
hard guardrails.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional


STRATEGY_CODE = "multi_layer_regime_rotation_v2"
STRATEGY_VERSION_CODE = "v1_l0_l12_state_budget_theme_style"


@dataclass(frozen=True)
class R64GuardrailState:
    block_signal_generation: bool = True
    block_trading: bool = True
    formal_signal_allowed: bool = False
    trading_allowed: bool = False

    def assert_safe(self) -> None:
        if self.formal_signal_allowed or self.trading_allowed:
            raise RuntimeError("R64 adapter skeleton must not release formal signals or trading.")
        if not self.block_signal_generation or not self.block_trading:
            raise RuntimeError("R64 adapter skeleton guardrails are not blocking signal/trading.")


@dataclass(frozen=True)
class R64AdapterConfig:
    schema_name: str = "research_ops"
    strategy_code: str = STRATEGY_CODE
    strategy_version_code: str = STRATEGY_VERSION_CODE
    full_decision_version: str = "r64_l0_l12_state_skeleton_v3"
    plan_version: str = "r64_prototype_candidate_plan_v1"
    backtest_version: str = "r64_research_prototype_backtest_dryrun_v1"
    top_n: int = 50


class MultiLayerRegimeRotationV2ResearchAdapter:
    """Research-only candidate adapter.

    Expected input rows come from research_ops snapshots:
    - research_layer_decision_snapshot
    - research_strategy_candidate_plan_snapshot
    - research_strategy_backtest_result_snapshot

    C2 only defines the adapter shell. DB readers are wired in the next stage.
    """

    def __init__(self, config: Optional[R64AdapterConfig] = None, guardrails: Optional[R64GuardrailState] = None) -> None:
        self.config = config or R64AdapterConfig()
        self.guardrails = guardrails or R64GuardrailState()
        self.guardrails.assert_safe()

    def validate_context(self, *, strategy_code: str, strategy_version_code: str) -> None:
        if strategy_code != self.config.strategy_code:
            raise ValueError(f"unexpected strategy_code: {strategy_code}")
        if strategy_version_code != self.config.strategy_version_code:
            raise ValueError(f"unexpected strategy_version_code: {strategy_version_code}")
        self.guardrails.assert_safe()

    def build_candidate_preview(
        self,
        *,
        decision_rows: Iterable[Mapping[str, Any]],
        candidate_rows: Iterable[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        self.guardrails.assert_safe()
        decisions = list(decision_rows)
        candidates = list(candidate_rows)
        top = candidates[: max(0, int(self.config.top_n))]
        return {
            "strategy_code": self.config.strategy_code,
            "strategy_version_code": self.config.strategy_version_code,
            "full_decision_version": self.config.full_decision_version,
            "plan_version": self.config.plan_version,
            "candidate_count": len(candidates),
            "preview_count": len(top),
            "decision_layer_count": len(decisions),
            "formal_signal_allowed": False,
            "trading_allowed": False,
            "block_signal_generation": True,
            "block_trading": True,
            "prototype_action": "SIMULATION_CANDIDATE",
            "candidates": top,
        }

    def build_signal_preview(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        self.guardrails.assert_safe()
        return {
            "strategy_code": self.config.strategy_code,
            "strategy_version_code": self.config.strategy_version_code,
            "formal_signal_allowed": False,
            "trading_allowed": False,
            "block_signal_generation": True,
            "block_trading": True,
            "signal_rows": [],
            "reason_code": "R64_SIGNAL_BLOCKED_RESEARCH_ONLY",
        }

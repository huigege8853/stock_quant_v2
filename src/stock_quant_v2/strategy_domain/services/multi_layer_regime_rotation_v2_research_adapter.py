"""Research-only adapter skeleton for R64 multi-layer regime rotation v2.

This module is intentionally conservative. It must not create formal strategy
signals or trading instructions until a later explicit release stage removes the
hard guardrails.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Mapping, Optional


STRATEGY_CODE = "multi_layer_regime_rotation_v2"
STRATEGY_VERSION_CODE = "v1_l0_l12_state_budget_theme_style"
R64_GATE_STATUS = "OBSERVE_ONLY"
R64_REASON_CODE = "R64_SIGNAL_BLOCKED_RESEARCH_ONLY"
R64_REASON_TEXT = (
    "R64 multi-layer regime rotation v2 remains research-only; "
    "formal signal generation and trading are blocked."
)
R64_SCORE = 0.0
R64_WEIGHT_ADJUSTMENT = 0.0
R64_SHADOW_ARTIFACT_VERSION = "r64_shadow_signal_artifact_v1"
R64_BACKTEST_REQUEST_DRYRUN_ARTIFACT_VERSION = "r64_m5_backtest_request_dryrun_candidate_v1"
R64_STRATEGY_COMPARE_INPUT_DRYRUN_ARTIFACT_VERSION = "r64_strategy_compare_input_dryrun_candidate_v1"
R64_REPORT_GENERATION_DRYRUN_ARTIFACT_VERSION = "r64_report_generation_dryrun_candidate_v1"


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
    shadow_artifact_version: str = R64_SHADOW_ARTIFACT_VERSION
    top_n: int = 50


class MultiLayerRegimeRotationV2ResearchAdapter:
    """Research-only candidate adapter.

    Expected input rows come from research_ops snapshots:
    - research_layer_decision_snapshot
    - research_strategy_candidate_plan_snapshot
    - research_strategy_backtest_result_snapshot

    R64E5 still emits dry-run shadow/backtest/compare/report-candidate artifacts. It does not write formal signals,
    create M5 backtest requests, execute backtests, create reports, trigger M7, or trade.
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

    def build_reason_schema_payload(
        self,
        *,
        source: str,
        extra_evidence: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Return the R64D minimum reason/evidence schema.

        This schema is intentionally OBSERVE_ONLY while R64 is still research-only.
        """
        self.guardrails.assert_safe()
        evidence: Dict[str, Any] = {
            "source": source,
            "schema_name": self.config.schema_name,
            "strategy_code": self.config.strategy_code,
            "strategy_version_code": self.config.strategy_version_code,
            "full_decision_version": self.config.full_decision_version,
            "plan_version": self.config.plan_version,
            "backtest_version": self.config.backtest_version,
            "shadow_artifact_version": self.config.shadow_artifact_version,
            "formal_signal_allowed": False,
            "trading_allowed": False,
            "block_signal_generation": True,
            "block_trading": True,
        }
        if extra_evidence:
            evidence.update(dict(extra_evidence))
        return {
            "gate_status": R64_GATE_STATUS,
            "score": R64_SCORE,
            "weight_adjustment": R64_WEIGHT_ADJUSTMENT,
            "reason_code": R64_REASON_CODE,
            "reason_text": R64_REASON_TEXT,
            "evidence_json": evidence,
        }

    def _json_safe(self, value: Any) -> Any:
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if isinstance(value, Mapping):
            return {str(key): self._json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._json_safe(item) for item in value]
        return value

    def _candidate_identity(self, row: Mapping[str, Any]) -> str:
        for key in ("ts_code", "security_code", "stock_code", "symbol", "code"):
            value = row.get(key)
            if value not in (None, ""):
                return str(value)
        return "UNKNOWN"

    def _candidate_score(self, row: Mapping[str, Any]) -> float:
        for key in ("score", "alpha_score", "candidate_score", "rank_score"):
            value = row.get(key)
            if value in (None, ""):
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return 0.0

    def build_shadow_candidate_rows(self, candidate_rows: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        """Build R64E1 shadow candidate rows without DB writes or formal signals."""
        self.guardrails.assert_safe()
        rows = list(candidate_rows)
        top = rows[: max(0, int(self.config.top_n))]
        shadow_rows: List[Dict[str, Any]] = []
        for rank, row in enumerate(top, start=1):
            row_dict = self._json_safe(dict(row))
            ts_code = self._candidate_identity(row)
            shadow_rows.append(
                {
                    "rank": rank,
                    "strategy_code": self.config.strategy_code,
                    "strategy_version_code": self.config.strategy_version_code,
                    "ts_code": ts_code,
                    "score": self._candidate_score(row),
                    "gate_status": R64_GATE_STATUS,
                    "artifact_type": "shadow_candidate_row",
                    "formal_signal_allowed": False,
                    "trading_allowed": False,
                    "block_signal_generation": True,
                    "block_trading": True,
                    "source_row": row_dict,
                }
            )
        return shadow_rows

    def build_shadow_signal_rows(self, candidate_rows: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        """Build blocked shadow signal rows for research comparison only.

        These rows are not formal strategy_signal rows. Target weights are zero
        by design until a later release stage explicitly removes the guardrails.
        """
        self.guardrails.assert_safe()
        shadow_candidates = self.build_shadow_candidate_rows(candidate_rows)
        shadow_signals: List[Dict[str, Any]] = []
        for row in shadow_candidates:
            shadow_signals.append(
                {
                    "rank": row["rank"],
                    "strategy_code": self.config.strategy_code,
                    "strategy_version_code": self.config.strategy_version_code,
                    "ts_code": row["ts_code"],
                    "score": row["score"],
                    "target_weight": 0.0,
                    "shadow_weight": 0.0,
                    "signal_action": "HOLD_SHADOW_ONLY",
                    "signal_status": "BLOCKED_RESEARCH_ONLY",
                    "gate_status": R64_GATE_STATUS,
                    "artifact_type": "shadow_signal_row",
                    "formal_signal_allowed": False,
                    "trading_allowed": False,
                    "block_signal_generation": True,
                    "block_trading": True,
                }
            )
        return shadow_signals

    def build_backtest_request_dryrun_candidate(self, *, shadow_signal_row_count: int = 0) -> Dict[str, Any]:
        """Return an M5-compatible dry-run backtest request candidate.

        This is an artifact payload only. It must not write DB rows, create a
        formal backtest request, generate formal signals, trigger M7, or trade.
        """
        self.guardrails.assert_safe()
        shadow_count = int(shadow_signal_row_count)
        evidence = {
            "source": "backtest_request_dryrun_candidate",
            "schema_name": self.config.schema_name,
            "strategy_code": self.config.strategy_code,
            "strategy_version_code": self.config.strategy_version_code,
            "backtest_version": self.config.backtest_version,
            "shadow_artifact_version": self.config.shadow_artifact_version,
            "shadow_signal_row_count": shadow_count,
            "formal_signal_allowed": False,
            "trading_allowed": False,
            "block_signal_generation": True,
            "block_trading": True,
            "db_write_allowed": False,
            "backtest_request_created": False,
            "create_mode": "DRY_RUN_ONLY",
        }
        return {
            "artifact_type": "backtest_request_dryrun_candidate",
            "artifact_version": R64_BACKTEST_REQUEST_DRYRUN_ARTIFACT_VERSION,
            "request_status": "DRY_RUN_NOT_CREATED",
            "create_mode": "DRY_RUN_ONLY",
            "db_write_allowed": False,
            "backtest_request_created": False,
            "formal_signal_allowed": False,
            "trading_allowed": False,
            "block_signal_generation": True,
            "block_trading": True,
            "gate_status": R64_GATE_STATUS,
            "score": R64_SCORE,
            "weight_adjustment": R64_WEIGHT_ADJUSTMENT,
            "reason_code": R64_REASON_CODE,
            "reason_text": R64_REASON_TEXT,
            "strategy_code": self.config.strategy_code,
            "strategy_version_code": self.config.strategy_version_code,
            "version_code": self.config.strategy_version_code,
            "backtest_version": self.config.backtest_version,
            "source": self.config.shadow_artifact_version,
            "source_artifact_type": "shadow_signal_artifact",
            "source_signal_run_id": None,
            "screen_request_id": None,
            "engine_code": "backtrader",
            "engine_payload": {
                "r64_shadow_only": True,
                "shadow_artifact_version": self.config.shadow_artifact_version,
                "shadow_signal_row_count": shadow_count,
                "formal_signal_allowed": False,
                "trading_allowed": False,
                "db_write_allowed": False,
                "backtest_request_created": False,
                "create_mode": "DRY_RUN_ONLY",
            },
            "evidence_json": evidence,
        }

    def build_backtest_request_candidate(self, *, shadow_signal_row_count: int = 0) -> Dict[str, Any]:
        """Backward-compatible alias for R64E1 payload readers."""
        return self.build_backtest_request_dryrun_candidate(
            shadow_signal_row_count=shadow_signal_row_count
        )

    def build_strategy_compare_input_dryrun_candidate(self, *, shadow_signal_row_count: int = 0) -> Dict[str, Any]:
        """Return a dry-run-only strategy compare input candidate.

        This payload is a bridge artifact for a later R64E compare/backtest stage.
        It must not execute a backtest, create a formal compare report, write DB
        rows, generate formal signals, trigger M7, or trade.
        """
        self.guardrails.assert_safe()
        backtest_candidate = self.build_backtest_request_dryrun_candidate(
            shadow_signal_row_count=shadow_signal_row_count
        )
        evidence = {
            "source": "strategy_compare_input_dryrun_candidate",
            "schema_name": self.config.schema_name,
            "strategy_code": self.config.strategy_code,
            "strategy_version_code": self.config.strategy_version_code,
            "backtest_version": self.config.backtest_version,
            "shadow_artifact_version": self.config.shadow_artifact_version,
            "backtest_request_dryrun_artifact_version": R64_BACKTEST_REQUEST_DRYRUN_ARTIFACT_VERSION,
            "strategy_compare_input_dryrun_artifact_version": R64_STRATEGY_COMPARE_INPUT_DRYRUN_ARTIFACT_VERSION,
            "shadow_signal_row_count": int(shadow_signal_row_count),
            "formal_signal_allowed": False,
            "trading_allowed": False,
            "block_signal_generation": True,
            "block_trading": True,
            "db_write_allowed": False,
            "backtest_request_created": False,
            "backtest_executed": False,
            "strategy_compare_report_created": False,
            "create_mode": "DRY_RUN_ONLY",
        }
        return {
            "artifact_type": "strategy_compare_input_dryrun_candidate",
            "artifact_version": R64_STRATEGY_COMPARE_INPUT_DRYRUN_ARTIFACT_VERSION,
            "compare_status": "DRY_RUN_NOT_EXECUTED",
            "compare_mode": "DRY_RUN_ONLY",
            "db_write_allowed": False,
            "backtest_request_created": False,
            "backtest_executed": False,
            "strategy_compare_report_created": False,
            "formal_signal_allowed": False,
            "trading_allowed": False,
            "block_signal_generation": True,
            "block_trading": True,
            "gate_status": R64_GATE_STATUS,
            "score": R64_SCORE,
            "weight_adjustment": R64_WEIGHT_ADJUSTMENT,
            "reason_code": R64_REASON_CODE,
            "reason_text": R64_REASON_TEXT,
            "strategy_code": self.config.strategy_code,
            "strategy_version_code": self.config.strategy_version_code,
            "version_code": self.config.strategy_version_code,
            "source_artifact_type": "backtest_request_dryrun_candidate",
            "source_artifact_version": R64_BACKTEST_REQUEST_DRYRUN_ARTIFACT_VERSION,
            "backtest_request_dryrun_candidate": backtest_candidate,
            "baseline_strategy_code": "regime_sector_industry_selection_v1",
            "baseline_label": "current_production_baseline",
            "benchmark_index_code": "000300.SH",
            "compare_dimensions": [
                "return",
                "drawdown",
                "turnover",
                "regime_performance",
                "coverage",
            ],
            "expected_reports": [
                "backtest_report",
                "walk_forward_report",
                "strategy_compare_report",
            ],
            "metrics_required": [
                "total_return",
                "annualized_return",
                "max_drawdown",
                "turnover",
                "win_rate",
                "exposure_ratio",
            ],
            "walk_forward_required": True,
            "evidence_json": evidence,
        }

    def build_report_generation_dryrun_candidate(self, *, shadow_signal_row_count: int = 0) -> Dict[str, Any]:
        """Return a dry-run-only report generation candidate for R64E documentation alignment.

        This payload aligns the R64E route-map report requirements without creating
        backtest_report, walk_forward_report, or strategy_compare_report artifacts.
        It must not execute backtests, write DB rows, generate formal signals,
        trigger M7, or trade.
        """
        self.guardrails.assert_safe()
        compare_input = self.build_strategy_compare_input_dryrun_candidate(
            shadow_signal_row_count=shadow_signal_row_count
        )
        evidence = {
            "source": "report_generation_dryrun_candidate",
            "schema_name": self.config.schema_name,
            "strategy_code": self.config.strategy_code,
            "strategy_version_code": self.config.strategy_version_code,
            "backtest_version": self.config.backtest_version,
            "shadow_artifact_version": self.config.shadow_artifact_version,
            "strategy_compare_input_dryrun_artifact_version": R64_STRATEGY_COMPARE_INPUT_DRYRUN_ARTIFACT_VERSION,
            "report_generation_dryrun_artifact_version": R64_REPORT_GENERATION_DRYRUN_ARTIFACT_VERSION,
            "shadow_signal_row_count": int(shadow_signal_row_count),
            "formal_signal_allowed": False,
            "trading_allowed": False,
            "block_signal_generation": True,
            "block_trading": True,
            "db_write_allowed": False,
            "backtest_request_created": False,
            "backtest_executed": False,
            "backtest_report_created": False,
            "walk_forward_report_created": False,
            "strategy_compare_report_created": False,
            "report_mode": "DRY_RUN_ONLY",
        }
        report_candidates = {
            "backtest_report_candidate": {
                "artifact_type": "backtest_report_dryrun_candidate",
                "report_name": "backtest_report",
                "status": "DRY_RUN_NOT_CREATED",
                "db_write_allowed": False,
                "backtest_executed": False,
                "report_created": False,
                "required_metrics": [
                    "total_return",
                    "annualized_return",
                    "max_drawdown",
                    "turnover",
                    "win_rate",
                    "exposure_ratio",
                ],
            },
            "walk_forward_report_candidate": {
                "artifact_type": "walk_forward_report_dryrun_candidate",
                "report_name": "walk_forward_report",
                "status": "DRY_RUN_NOT_CREATED",
                "db_write_allowed": False,
                "backtest_executed": False,
                "report_created": False,
                "required_dimensions": [
                    "train_window",
                    "validation_window",
                    "regime_segment",
                    "coverage",
                ],
            },
            "strategy_compare_report_candidate": {
                "artifact_type": "strategy_compare_report_dryrun_candidate",
                "report_name": "strategy_compare_report",
                "status": "DRY_RUN_NOT_CREATED",
                "db_write_allowed": False,
                "backtest_executed": False,
                "report_created": False,
                "baseline_strategy_code": "regime_sector_industry_selection_v1",
                "compare_dimensions": compare_input.get("compare_dimensions", []),
            },
        }
        return {
            "artifact_type": "report_generation_dryrun_candidate",
            "artifact_version": R64_REPORT_GENERATION_DRYRUN_ARTIFACT_VERSION,
            "report_status": "DRY_RUN_NOT_CREATED",
            "report_mode": "DRY_RUN_ONLY",
            "db_write_allowed": False,
            "backtest_request_created": False,
            "backtest_executed": False,
            "backtest_report_created": False,
            "walk_forward_report_created": False,
            "strategy_compare_report_created": False,
            "formal_signal_allowed": False,
            "trading_allowed": False,
            "block_signal_generation": True,
            "block_trading": True,
            "gate_status": R64_GATE_STATUS,
            "score": R64_SCORE,
            "weight_adjustment": R64_WEIGHT_ADJUSTMENT,
            "reason_code": R64_REASON_CODE,
            "reason_text": R64_REASON_TEXT,
            "strategy_code": self.config.strategy_code,
            "strategy_version_code": self.config.strategy_version_code,
            "version_code": self.config.strategy_version_code,
            "source_artifact_type": "strategy_compare_input_dryrun_candidate",
            "source_artifact_version": R64_STRATEGY_COMPARE_INPUT_DRYRUN_ARTIFACT_VERSION,
            "strategy_compare_input_dryrun_candidate": compare_input,
            "expected_reports": [
                "backtest_report",
                "walk_forward_report",
                "strategy_compare_report",
            ],
            "report_candidates": report_candidates,
            "result_contract_required": True,
            "result_contract_source": "strategy_backtest_result_contract_design_service",
            "evidence_json": evidence,
        }

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
        shadow_candidate_rows = self.build_shadow_candidate_rows(top)
        shadow_signal_rows = self.build_shadow_signal_rows(top)
        payload = {
            "strategy_code": self.config.strategy_code,
            "strategy_version_code": self.config.strategy_version_code,
            "full_decision_version": self.config.full_decision_version,
            "plan_version": self.config.plan_version,
            "backtest_version": self.config.backtest_version,
            "shadow_artifact_version": self.config.shadow_artifact_version,
            "candidate_count": len(candidates),
            "preview_count": len(top),
            "decision_layer_count": len(decisions),
            "formal_signal_allowed": False,
            "trading_allowed": False,
            "block_signal_generation": True,
            "block_trading": True,
            "prototype_action": "SIMULATION_CANDIDATE",
            "candidates": [self._json_safe(dict(row)) for row in top],
            "shadow_candidate_rows": shadow_candidate_rows,
            "shadow_signal_rows": shadow_signal_rows,
            "signal_rows": [],
            "backtest_request_dryrun_candidate": self.build_backtest_request_dryrun_candidate(
                shadow_signal_row_count=len(shadow_signal_rows)
            ),
            "backtest_request_candidate": self.build_backtest_request_dryrun_candidate(
                shadow_signal_row_count=len(shadow_signal_rows)
            ),
            "strategy_compare_input_dryrun_candidate": self.build_strategy_compare_input_dryrun_candidate(
                shadow_signal_row_count=len(shadow_signal_rows)
            ),
            "strategy_compare_input": self.build_strategy_compare_input_dryrun_candidate(
                shadow_signal_row_count=len(shadow_signal_rows)
            ),
            "report_generation_dryrun_candidate": self.build_report_generation_dryrun_candidate(
                shadow_signal_row_count=len(shadow_signal_rows)
            ),
            "report_generation_candidate": self.build_report_generation_dryrun_candidate(
                shadow_signal_row_count=len(shadow_signal_rows)
            ),
        }
        payload.update(
            self.build_reason_schema_payload(
                source="candidate_preview",
                extra_evidence={
                    "candidate_count": len(candidates),
                    "preview_count": len(top),
                    "decision_layer_count": len(decisions),
                    "shadow_candidate_row_count": len(shadow_candidate_rows),
                    "shadow_signal_row_count": len(shadow_signal_rows),
                    "backtest_request_created": False,
                    "backtest_executed": False,
                    "strategy_compare_report_created": False,
                    "backtest_report_created": False,
                    "walk_forward_report_created": False,
                    "db_write_allowed": False,
                    "prototype_action": "SIMULATION_CANDIDATE",
                },
            )
        )
        return payload

    def build_signal_preview(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        self.guardrails.assert_safe()
        payload = {
            "strategy_code": self.config.strategy_code,
            "strategy_version_code": self.config.strategy_version_code,
            "formal_signal_allowed": False,
            "trading_allowed": False,
            "block_signal_generation": True,
            "block_trading": True,
            "signal_rows": [],
            "shadow_candidate_rows": [],
            "shadow_signal_rows": [],
            "backtest_request_dryrun_candidate": self.build_backtest_request_dryrun_candidate(shadow_signal_row_count=0),
            "backtest_request_candidate": self.build_backtest_request_dryrun_candidate(shadow_signal_row_count=0),
            "strategy_compare_input_dryrun_candidate": self.build_strategy_compare_input_dryrun_candidate(shadow_signal_row_count=0),
            "strategy_compare_input": self.build_strategy_compare_input_dryrun_candidate(shadow_signal_row_count=0),
            "report_generation_dryrun_candidate": self.build_report_generation_dryrun_candidate(shadow_signal_row_count=0),
            "report_generation_candidate": self.build_report_generation_dryrun_candidate(shadow_signal_row_count=0),
        }
        payload.update(
            self.build_reason_schema_payload(
                source="signal_preview",
                extra_evidence={
                    "signal_rows": 0,
                    "shadow_candidate_row_count": 0,
                    "shadow_signal_row_count": 0,
                    "backtest_request_created": False,
                    "backtest_executed": False,
                    "strategy_compare_report_created": False,
                    "backtest_report_created": False,
                    "walk_forward_report_created": False,
                    "db_write_allowed": False,
                    "prototype_action": "SIGNAL_PREVIEW_BLOCKED",
                },
            )
        )
        return payload

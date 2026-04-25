from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from stock_quant_v2.db.models.ops import OpsRunArtifact
from stock_quant_v2.research_domain.adapters import (
    BacktraderAnalyzerBridge,
    BacktraderDataFeedAdapter,
    BacktraderStrategyBridge,
)
from stock_quant_v2.research_domain.repositories import (
    BacktestRepository,
    RunResultRepository,
)
from stock_quant_v2.research_domain.enums import ArtifactType, StorageBackend


class BacktestExecutionPlanService:
    def __init__(self, session: Session):
        self.session = session
        self.backtest_repo = BacktestRepository(session)
        self.run_result_repo = RunResultRepository(session)
        self.strategy_bridge = BacktraderStrategyBridge(session)
        self.datafeed_adapter = BacktraderDataFeedAdapter(session)
        self.analyzer_bridge = BacktraderAnalyzerBridge()

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, dict):
            return {k: BacktestExecutionPlanService._json_safe(v) for k, v in value.items()}
        if isinstance(value, list):
            return [BacktestExecutionPlanService._json_safe(v) for v in value]
        return value

    def _latest_request_id(self) -> int:
        request = self.backtest_repo.get_latest_request()
        if request is None:
            raise RuntimeError("no backtest_request found")
        return int(request.id)

    def build_execution_plan(
        self,
        *,
        backtest_request_id: int | None = None,
    ) -> dict[str, Any]:
        if backtest_request_id is None:
            backtest_request_id = self._latest_request_id()

        request = self.backtest_repo.get_request_by_id(backtest_request_id)

        strategy_plan = self.strategy_bridge.build_strategy_plan(request=request)
        instrument_ids = strategy_plan.get("instrument_ids", [])

        data_feed_plan = self.datafeed_adapter.build_data_feed_plan(
            request=request,
            instrument_ids=instrument_ids,
        )

        analyzer_plan = self.analyzer_bridge.build_analyzer_plan(
            request=request,
            data_feed_plan=data_feed_plan,
            strategy_bridge_plan=strategy_plan,
        )

        execution_plan = {
            "stage": "M5.6_BACKTRADER_ADAPTER_CONTRACT_SKELETON",
            "execution_enabled": False,
            "run_id": request.run_id,
            "backtest_request_id": request.id,
            "start_date": request.start_date,
            "end_date": request.end_date,
            "engine_code": request.engine_code,
            "source_signal_run_id": request.source_signal_run_id,
            "screen_request_id": request.screen_request_id,
            "execution_assumption_profile_id": request.execution_assumption_profile_id,
            "benchmark_definition_id": request.benchmark_definition_id,
            "data_feed_plan": data_feed_plan,
            "strategy_bridge_plan": strategy_plan,
            "analyzer_bridge_plan": analyzer_plan,
        }

        safe_plan = self._json_safe(execution_plan)
        artifact = self._write_execution_plan_artifact(
            run_id=request.run_id,
            plan=safe_plan,
        )

        self.run_result_repo.replace_backtest_metrics(
            run_id=request.run_id,
            metrics={
                "backtest_request_id": request.id,
                "strategy_version_id": request.strategy_version_id,
                "source_signal_run_id": request.source_signal_run_id,
                "screen_request_id": request.screen_request_id,
                "execution_assumption_profile_id": request.execution_assumption_profile_id,
                "initial_cash": request.initial_cash,
                "execution_enabled": False,
                "signal_selected_count": strategy_plan.get("selected_count"),
                "signal_instrument_count": strategy_plan.get("instrument_count"),
                "data_bar_rows": data_feed_plan.get("bar_rows"),
                "data_trade_day_count": data_feed_plan.get("trade_day_count"),
                "data_covered_instrument_count": data_feed_plan.get(
                    "covered_instrument_count"
                ),
            },
        )

        self.session.commit()

        return {
            "run_id": request.run_id,
            "backtest_request_id": request.id,
            "artifact_id": artifact.id,
            "artifact_code": artifact.artifact_code,
            "artifact_uri": artifact.uri,
            "execution_enabled": False,
            "strategy_selected_count": strategy_plan.get("selected_count"),
            "strategy_instrument_count": strategy_plan.get("instrument_count"),
            "data_bar_rows": data_feed_plan.get("bar_rows"),
            "data_trade_day_count": data_feed_plan.get("trade_day_count"),
            "data_status": data_feed_plan.get("status"),
            "analyzer_metric_targets": analyzer_plan.get("planned_metric_targets"),
            "note": "M5.6 execution plan generated; backtrader not started",
        }

    def _write_execution_plan_artifact(
        self,
        *,
        run_id: int,
        plan: dict[str, Any],
    ) -> OpsRunArtifact:
        artifact_dir = Path("artifacts") / "m5" / "backtest"
        artifact_dir.mkdir(parents=True, exist_ok=True)

        artifact_path = artifact_dir / f"backtest_execution_plan_run_{run_id}.json"
        artifact_path.write_text(
            json.dumps(plan, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        existing = (
            self.session.query(OpsRunArtifact)
            .filter(
                OpsRunArtifact.run_id == run_id,
                OpsRunArtifact.artifact_code == "backtest_execution_plan_json",
            )
            .one_or_none()
        )

        if existing is None:
            existing = OpsRunArtifact(
                run_id=run_id,
                artifact_type=ArtifactType.JSON.value,
                artifact_code="backtest_execution_plan_json",
                artifact_name="Backtest Execution Plan JSON",
                storage_backend=StorageBackend.LOCAL.value,
                uri=str(artifact_path),
                mime_type="application/json",
                file_size_bytes=artifact_path.stat().st_size,
                checksum_sha256=None,
                payload_schema=None,
                artifact_metadata={
                    "stage": "M5.6_BACKTRADER_ADAPTER_CONTRACT_SKELETON",
                    "execution_enabled": False,
                },
            )
            self.session.add(existing)
        else:
            existing.artifact_type = ArtifactType.JSON.value
            existing.artifact_name = "Backtest Execution Plan JSON"
            existing.storage_backend = StorageBackend.LOCAL.value
            existing.uri = str(artifact_path)
            existing.mime_type = "application/json"
            existing.file_size_bytes = artifact_path.stat().st_size
            existing.artifact_metadata = {
                "stage": "M5.6_BACKTRADER_ADAPTER_CONTRACT_SKELETON",
                "execution_enabled": False,
            }

        self.session.flush()
        return existing
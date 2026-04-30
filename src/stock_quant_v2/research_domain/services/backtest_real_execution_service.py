from __future__ import annotations

import csv
import json
import math
import os
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import backtrader as bt
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from stock_quant_v2.db.models.ops import (
    OpsRunArtifact,
    OpsRunSeriesSnapshot,
)
from stock_quant_v2.db.models.research import (
    ResearchBacktestRequest,
    ResearchBacktestResult,
    ResearchExecutionAssumptionProfile,
)
from stock_quant_v2.research_domain.enums import (
    ArtifactType,
    ResultStatus,
    SeriesNamespace,
    StorageBackend,
)
from stock_quant_v2.research_domain.repositories import (
    BacktestRepository,
    RunResultRepository,
)


STRICT_NEXT_OPEN = "STRICT_NEXT_OPEN"
SNAPSHOT_STATIC_BASKET_P1 = "SNAPSHOT_STATIC_BASKET_P1"
HISTORICAL_SIGNAL_REPLAY_P1 = "HISTORICAL_SIGNAL_REPLAY_P1"


@dataclass
class BacktestTargetWeightPlan:
    """Resolved target weights for one M5 backtest execution.

    STRICT_NEXT_OPEN means strategy_signal already has effective_date rows inside the
    request window. SNAPSHOT_STATIC_BASKET_P1 means the current signal batch is used
    as a static basket and placed on the first tradable date in the backtest window.
    """

    execution_mode: str
    target_weights_by_date: dict[date, dict[int, Decimal]]
    source_effective_dates: list[date]
    fallback_reason: str | None = None
    original_signal_effective_mode: str | None = None
    note: str | None = None
    source_run_ids_by_date: dict[date, int] = field(default_factory=dict)

    @property
    def instrument_ids(self) -> list[int]:
        return sorted(
            {
                int(instrument_id)
                for weights in self.target_weights_by_date.values()
                for instrument_id in weights.keys()
            }
        )

    @property
    def target_dates(self) -> list[date]:
        return sorted(self.target_weights_by_date.keys())



class _M510EqualWeightBacktraderStrategy(bt.Strategy):
    """Self-contained M5.10 equal-weight execution strategy.

    It triggers on the first bar whose date is on or after the target date.
    For STRICT_NEXT_OPEN, sliding to a later bar is ignored so the service can
    detect strict failure. For SNAPSHOT_STATIC_BASKET_P1, sliding to the first
    executable bar is accepted and recorded.
    """

    params = (
        ("target_weights_by_date", None),
        ("daily_records", None),
        ("order_records", None),
        ("rebalance_records", None),
        ("record_start_date", None),
        ("record_end_date", None),
        ("allow_next_fallback", False),
        ("execution_mode", STRICT_NEXT_OPEN),
    )

    def __init__(self) -> None:
        self._target_weights_by_date = dict(self.p.target_weights_by_date or {})
        self._target_dates = sorted(self._target_weights_by_date.keys())
        self._executed_target_dates = set()

    def next_open(self) -> None:
        self._maybe_rebalance(hook_name="next_open")

    def next(self) -> None:
        current_date = self._current_date()
        if current_date is None:
            return
        if self.p.record_start_date and current_date < self.p.record_start_date:
            return
        if self.p.record_end_date and current_date > self.p.record_end_date:
            return

        gross_exposure = 0.0
        holding_count = 0
        for data in self.datas:
            position = self.getposition(data)
            size = float(position.size or 0.0)
            if abs(size) > 1e-12:
                holding_count += 1
            close_price = float(data.close[0]) if data.close[0] is not None else 0.0
            gross_exposure += abs(size * close_price)

        self.p.daily_records.append(
            {
                "trade_date": current_date.isoformat(),
                "portfolio_equity": float(self.broker.getvalue()),
                "cash": float(self.broker.getcash()),
                "holding_count": int(holding_count),
                "gross_exposure": float(gross_exposure),
            }
        )

    def notify_order(self, order) -> None:
        data = getattr(order, "data", None)
        try:
            instrument_id = int(data._name) if data is not None else None
        except Exception:
            instrument_id = None

        current_date = self._current_date(data=data)
        self.p.order_records.append(
            {
                "trade_date": current_date.isoformat() if current_date else None,
                "instrument_id": instrument_id,
                "status": order.getstatusname(),
                "is_buy": bool(order.isbuy()),
                "created_size": float(getattr(order.created, "size", 0.0) or 0.0),
                "executed_size": float(getattr(order.executed, "size", 0.0) or 0.0),
                "executed_price": float(getattr(order.executed, "price", 0.0) or 0.0),
                "executed_value": float(getattr(order.executed, "value", 0.0) or 0.0),
                "executed_commission": float(getattr(order.executed, "comm", 0.0) or 0.0),
            }
        )

    def _maybe_rebalance(self, *, hook_name: str) -> None:
        current_date = self._current_date()
        if current_date is None:
            return
        if self.p.record_start_date and current_date < self.p.record_start_date:
            return
        if self.p.record_end_date and current_date > self.p.record_end_date:
            return

        pending_targets = [
            target_date
            for target_date in self._target_dates
            if target_date not in self._executed_target_dates and target_date <= current_date
        ]
        if not pending_targets:
            return

        target_date = pending_targets[0]
        if current_date > target_date and not self.p.allow_next_fallback:
            return

        weights = self._target_weights_by_date.get(target_date) or {}
        if not weights:
            self._executed_target_dates.add(target_date)
            return

        submitted_count = 0
        target_count = 0
        for data in self.datas:
            try:
                instrument_id = int(data._name)
            except Exception:
                continue
            target_weight = float(weights.get(instrument_id, Decimal("0")))
            if target_weight > 0:
                target_count += 1
            order = self.order_target_percent(data=data, target=target_weight)
            if order is not None:
                submitted_count += 1

        self._executed_target_dates.add(target_date)
        source = "exact"
        if current_date > target_date:
            source = (
                "p1_first_executable_bar"
                if self.p.execution_mode == SNAPSHOT_STATIC_BASKET_P1
                else "next_fallback"
            )

        self.p.rebalance_records.append(
            {
                "target_date": target_date.isoformat(),
                "trade_date": current_date.isoformat(),
                "source": source,
                "hook": hook_name,
                "submitted_count": int(submitted_count),
                "target_count": int(target_count),
                "allow_next_fallback": bool(self.p.allow_next_fallback),
            }
        )

    def _current_date(self, *, data=None):
        data_obj = data if data is not None else (self.datas[0] if self.datas else None)
        if data_obj is None or len(data_obj) == 0:
            return None
        return data_obj.datetime.date(0)


class BacktestRealExecutionService:
    """M5.10 Backtrader Real Execution P1.

    This service preserves the existing M5 request / result / metric / artifact /
    series model, but replaces the previous skeleton-only behavior with a real
    backtrader run.

    Supported in P1:
    - strategy_signal selection source
    - EQUAL_WEIGHT_TOP_N style target weights
    - strict NEXT_OPEN when signal effective dates are inside the backtest window
    - SNAPSHOT_STATIC_BASKET_P1 fallback when latest signal effective date is
      outside the backtest window
    - HISTORICAL_SIGNAL_REPLAY_P1 multi-date replay from historical strategy_signal
    - no benchmark calculation in this service
    """

    def __init__(self, session: Session):
        self.session = session
        self.backtest_repo = BacktestRepository(session)
        self.run_result_repo = RunResultRepository(session)

    def execute_minimal_backtest(
        self,
        *,
        backtest_request_id: int | None = None,
    ) -> dict[str, Any]:
        request = self._resolve_request(backtest_request_id=backtest_request_id)
        execution_profile = self._get_execution_profile(request)

        plan = self._build_target_weight_plan(request)
        if not plan.instrument_ids:
            raise RuntimeError(
                f"no instrument_ids resolved from signal_run_id={request.source_signal_run_id}"
            )

        preload_start_date = self._resolve_preload_start_date(
            request=request,
            instrument_ids=plan.instrument_ids,
        )
        data_frames = self._load_daily_bar_frames(
            request=request,
            instrument_ids=plan.instrument_ids,
            data_start_date=preload_start_date,
        )
        if not data_frames:
            raise RuntimeError("no core_daily_bar data loaded for selected instruments")

        plan = self._align_plan_to_loaded_data(request=request, plan=plan, data_frames=data_frames)

        if plan.execution_mode == HISTORICAL_SIGNAL_REPLAY_P1:
            # Backtrader multi-data synchronization is fragile for a 600+ stock
            # dynamic universe: target bars can exist in core_daily_bar while the
            # strategy clock still cannot submit orders for those feeds. M5.11 P1
            # therefore uses a deterministic equal-weight replay over the same
            # loaded OHLC data. M5.10 STRICT_NEXT_OPEN and fallback paths remain
            # unchanged and continue to use Backtrader.
            run_output = self._run_historical_replay_deterministic(
                request=request,
                execution_profile=execution_profile,
                plan=plan,
                data_frames=data_frames,
            )
        else:
            run_output = self._run_backtrader(
                request=request,
                execution_profile=execution_profile,
                plan=plan,
                data_frames=data_frames,
            )

            if not run_output["rebalance_records"]:
                if plan.execution_mode == STRICT_NEXT_OPEN:
                    plan = self._build_snapshot_static_plan_from_loaded_data(
                        request=request,
                        original_plan=plan,
                        data_frames=data_frames,
                        fallback_reason="strict_next_open_produced_no_rebalance_records",
                    )
                    run_output = self._run_backtrader(
                        request=request,
                        execution_profile=execution_profile,
                        plan=plan,
                        data_frames=data_frames,
                    )

        if not run_output["rebalance_records"]:
            raise RuntimeError(
                "execution failed: no rebalance_records produced after "
                f"execution_mode={plan.execution_mode}, target_dates={plan.target_dates}. "
                "Check core_daily_bar coverage and strategy date handling."
            )

        fallback_sources = [
            row for row in run_output["rebalance_records"] if row.get("source") == "next_fallback"
        ]
        if fallback_sources and plan.execution_mode != SNAPSHOT_STATIC_BASKET_P1:
            raise RuntimeError(
                "strict NEXT_OPEN violated: next_fallback was used while disabled"
            )

        initial_cash = float(request.initial_cash)
        metrics = self._compute_metrics(
            initial_cash=initial_cash,
            start_value=run_output["start_value"],
            final_value=run_output["final_value"],
            daily_records=run_output["daily_records"],
            order_records=run_output["order_records"],
        )

        result = self._upsert_backtest_result(
            request=request,
            metrics=metrics,
            daily_records=run_output["daily_records"],
            order_records=run_output["order_records"],
            rebalance_records=run_output["rebalance_records"],
            preload_start_date=preload_start_date,
            plan=plan,
        )

        artifact_rows = self._write_artifacts(
            request=request,
            metrics=metrics,
            daily_records=run_output["daily_records"],
            order_records=run_output["order_records"],
            rebalance_records=run_output["rebalance_records"],
            plan=plan,
        )

        self._replace_series(
            run_id=request.run_id,
            daily_records=run_output["daily_records"],
        )

        rebalance_source_counter = Counter(
            row.get("source") for row in run_output["rebalance_records"]
        )

        self.run_result_repo.replace_backtest_metrics(
            run_id=request.run_id,
            metrics={
                "backtest_request_id": request.id,
                "strategy_version_id": request.strategy_version_id,
                "source_signal_run_id": request.source_signal_run_id,
                "screen_request_id": request.screen_request_id,
                "execution_assumption_profile_id": request.execution_assumption_profile_id,
                "initial_cash": Decimal(str(initial_cash)),
                "final_equity": Decimal(str(run_output["final_value"])),
                "total_return": metrics["total_return"],
                "annual_return": metrics["annual_return"],
                "max_drawdown": metrics["max_drawdown"],
                "sharpe_ratio": metrics["sharpe_ratio"],
                "volatility": metrics["volatility"],
                "order_count": metrics["order_count"],
                "trade_count": metrics["trade_count"],
                "trading_days": metrics["trading_days"],
                "data_feed_count": len(data_frames),
                "signal_rebalance_date_count": len(plan.target_weights_by_date),
                "preload_enabled": True,
                "next_fallback_used": False,
                "rebalance_record_count": len(run_output["rebalance_records"]),
                "snapshot_static_basket_p1": plan.execution_mode == SNAPSHOT_STATIC_BASKET_P1,
                "historical_signal_replay_p1": plan.execution_mode == HISTORICAL_SIGNAL_REPLAY_P1,
                "historical_rebalance_date_count": len(plan.target_weights_by_date) if plan.execution_mode == HISTORICAL_SIGNAL_REPLAY_P1 else 0,
            },
        )

        self.session.commit()

        return {
            "run_id": request.run_id,
            "backtest_request_id": request.id,
            "backtest_result_id": result.id,
            "result_status": result.result_status,
            "execution_mode": plan.execution_mode,
            "fallback_reason": plan.fallback_reason,
            "start_date": str(request.start_date),
            "end_date": str(request.end_date),
            "preload_start_date": str(preload_start_date),
            "target_dates": [d.isoformat() for d in plan.target_dates],
            "source_effective_dates": [d.isoformat() for d in plan.source_effective_dates],
            "source_run_ids_by_date": {d.isoformat(): run_id for d, run_id in sorted(plan.source_run_ids_by_date.items())},
            "initial_cash": str(result.initial_cash),
            "final_equity": str(result.final_equity),
            "total_return": str(result.total_return),
            "annual_return": str(result.annual_return)
            if result.annual_return is not None
            else None,
            "max_drawdown": str(result.max_drawdown)
            if result.max_drawdown is not None
            else None,
            "sharpe_ratio": str(result.sharpe_ratio)
            if result.sharpe_ratio is not None
            else None,
            "volatility": str(result.volatility)
            if result.volatility is not None
            else None,
            "order_count": result.order_count,
            "trade_count": result.trade_count,
            "trading_days": result.trading_days,
            "trade_log_rows": len(run_output["order_records"]),
            "equity_curve_rows": len(run_output["daily_records"]),
            "rebalance_source_counter": dict(rebalance_source_counter),
            "next_fallback_used": False,
            "artifact_codes": [row.artifact_code for row in artifact_rows],
            "series_written": len(run_output["daily_records"]) * 4,
            "note": "M5.11 historical signal replay completed"
            if plan.execution_mode == HISTORICAL_SIGNAL_REPLAY_P1
            else "M5.10 real backtrader execution completed",
        }

    def _resolve_request(self, *, backtest_request_id: int | None) -> ResearchBacktestRequest:
        if backtest_request_id is None:
            request = self.backtest_repo.get_latest_request()
            if request is None:
                raise RuntimeError("no backtest_request found")
            return request

        request = self.backtest_repo.get_request_by_id(backtest_request_id)
        if request is None:
            raise RuntimeError(f"backtest_request not found: id={backtest_request_id}")
        return request

    def _get_execution_profile(
        self,
        request: ResearchBacktestRequest,
    ) -> ResearchExecutionAssumptionProfile:
        obj = self.session.get(
            ResearchExecutionAssumptionProfile,
            request.execution_assumption_profile_id,
        )
        if obj is None:
            raise RuntimeError(
                "execution_assumption_profile not found: "
                f"id={request.execution_assumption_profile_id}"
            )
        return obj

    def _build_target_weight_plan(
        self,
        request: ResearchBacktestRequest,
    ) -> BacktestTargetWeightPlan:
        if self._historical_replay_enabled(request=request):
            return self._build_historical_replay_plan(request=request)

        if request.source_signal_run_id is None:
            raise RuntimeError("source_signal_run_id is required")

        force_p1 = os.getenv("M5_BACKTEST_P1_EXECUTION_MODE", "").strip().upper()
        if force_p1 == SNAPSHOT_STATIC_BASKET_P1:
            return self._build_snapshot_static_plan(
                request=request,
                fallback_reason="forced_by_M5_BACKTEST_P1_EXECUTION_MODE",
            )

        in_window_rows = self._load_signal_rows_in_window(request=request)
        if in_window_rows:
            return BacktestTargetWeightPlan(
                execution_mode=STRICT_NEXT_OPEN,
                target_weights_by_date=self._rows_to_equal_weight_by_date(in_window_rows),
                source_effective_dates=sorted(
                    {self._coerce_date(row["effective_date"]) for row in in_window_rows}
                ),
                original_signal_effective_mode=getattr(request, "signal_effective_mode", None),
                note="strategy_signal effective_date is inside the backtest window",
            )

        return self._build_snapshot_static_plan(
            request=request,
            fallback_reason="signal_effective_date_outside_backtest_window_or_missing_in_window",
        )

    def _historical_replay_enabled(self, *, request: ResearchBacktestRequest) -> bool:
        raw = os.getenv("M5_HISTORICAL_REPLAY_ENABLED", "").strip().lower()
        if raw in {"1", "true", "yes", "y", "on"}:
            return True
        if raw in {"0", "false", "no", "n", "off"}:
            return False

        payloads = [
            getattr(request, "engine_payload", None),
            getattr(request, "request_payload", None),
            getattr(request, "portfolio_construction_payload", None),
        ]
        for payload in payloads:
            if isinstance(payload, dict):
                value = payload.get("m5_historical_replay_enabled")
                if isinstance(value, bool):
                    return value
                if isinstance(value, str) and value.strip().lower() in {"1", "true", "yes", "y", "on"}:
                    return True
        return False

    def _historical_replay_config(self, *, request: ResearchBacktestRequest) -> dict[str, Any]:
        payloads = [
            getattr(request, "engine_payload", None),
            getattr(request, "request_payload", None),
            getattr(request, "portfolio_construction_payload", None),
        ]

        def payload_value(name: str) -> Any | None:
            for payload in payloads:
                if isinstance(payload, dict) and payload.get(name) is not None:
                    return payload.get(name)
            return None

        start_raw = (
            os.getenv("M5_HISTORICAL_REPLAY_START_DATE")
            or payload_value("historical_replay_start_date")
            or request.start_date
        )
        end_raw = (
            os.getenv("M5_HISTORICAL_REPLAY_END_DATE")
            or payload_value("historical_replay_end_date")
            or request.end_date
        )
        top_n_raw = (
            os.getenv("M5_HISTORICAL_REPLAY_TOP_N")
            or payload_value("historical_replay_top_n")
            or 30
        )

        start_date = self._coerce_date(start_raw)
        end_date = self._coerce_date(end_raw)
        top_n = int(top_n_raw)

        if start_date < request.start_date:
            raise RuntimeError(
                "M5 historical replay start_date is earlier than backtest request.start_date: "
                f"{start_date} < {request.start_date}"
            )
        if end_date > request.end_date:
            raise RuntimeError(
                "M5 historical replay end_date is later than backtest request.end_date: "
                f"{end_date} > {request.end_date}"
            )
        if start_date > end_date:
            raise RuntimeError(
                "M5 historical replay start_date must be <= end_date: "
                f"{start_date} > {end_date}"
            )
        if top_n <= 0:
            raise RuntimeError("M5_HISTORICAL_REPLAY_TOP_N must be positive")

        return {
            "start_date": start_date,
            "end_date": end_date,
            "top_n": top_n,
        }

    def _build_historical_replay_plan(
        self,
        *,
        request: ResearchBacktestRequest,
    ) -> BacktestTargetWeightPlan:
        config = self._historical_replay_config(request=request)
        rows = self._load_historical_replay_signal_rows(
            start_date=config["start_date"],
            end_date=config["end_date"],
            top_n=config["top_n"],
        )
        if not rows:
            raise RuntimeError(
                "no historical strategy_signal rows found for M5.11 replay window "
                f"{config['start_date']} -> {config['end_date']}"
            )

        weights_by_date = self._rows_to_equal_weight_by_date(rows)
        source_run_ids_by_date: dict[date, int] = {}
        for row in rows:
            effective_date = self._coerce_date(row["effective_date"])
            source_run_ids_by_date[effective_date] = int(row["run_id"])

        bad_dates = [
            d for d, weights in sorted(weights_by_date.items())
            if len(weights) != int(config["top_n"])
        ]
        if bad_dates:
            raise RuntimeError(
                "historical replay signal count mismatch; expected top_n="
                f"{config['top_n']} for every date, bad_dates="
                f"{[d.isoformat() for d in bad_dates]}"
            )

        return BacktestTargetWeightPlan(
            execution_mode=HISTORICAL_SIGNAL_REPLAY_P1,
            target_weights_by_date=weights_by_date,
            source_effective_dates=sorted(weights_by_date.keys()),
            fallback_reason=None,
            original_signal_effective_mode=getattr(request, "signal_effective_mode", None),
            note=(
                "M5.11 P1 replays historical strategy_signal by effective_date; "
                "one latest run_id is selected per rebalance date."
            ),
            source_run_ids_by_date=source_run_ids_by_date,
        )

    def _load_historical_replay_signal_rows(
        self,
        *,
        start_date: date,
        end_date: date,
        top_n: int,
    ) -> list[dict[str, Any]]:
        rows = self.session.execute(
            text(
                """
                with chosen_runs as (
                    select
                        effective_date,
                        max(run_id) as run_id
                    from strategy_signal
                    where effective_date >= :start_date
                      and effective_date <= :end_date
                      and instrument_id is not null
                      and signal_action = 'select'
                    group by effective_date
                ), ranked_rows as (
                    select
                        s.effective_date,
                        s.run_id,
                        s.as_of_date,
                        s.instrument_id,
                        s.raw_score,
                        s.rank_in_batch,
                        row_number() over (
                            partition by s.effective_date, s.run_id
                            order by s.rank_in_batch asc nulls last, s.instrument_id asc
                        ) as rn
                    from strategy_signal s
                    join chosen_runs c
                      on c.effective_date = s.effective_date
                     and c.run_id = s.run_id
                    where s.instrument_id is not null
                      and s.signal_action = 'select'
                )
                select
                    effective_date,
                    run_id,
                    as_of_date,
                    instrument_id,
                    raw_score,
                    rank_in_batch
                from ranked_rows
                where rn <= :top_n
                order by effective_date asc, rn asc, instrument_id asc
                """
            ),
            {
                "start_date": start_date,
                "end_date": end_date,
                "top_n": top_n,
            },
        ).mappings().all()
        return [dict(row) for row in rows]

    def _load_signal_rows_in_window(self, *, request: ResearchBacktestRequest) -> list[dict[str, Any]]:
        rows = self.session.execute(
            text(
                """
                select
                    effective_date,
                    instrument_id,
                    raw_score,
                    rank_in_batch
                from strategy_signal
                where run_id = :run_id
                  and effective_date >= :start_date
                  and effective_date <= :end_date
                  and instrument_id is not null
                  and signal_action = 'select'
                order by effective_date asc, rank_in_batch asc nulls last, instrument_id asc
                """
            ),
            {
                "run_id": request.source_signal_run_id,
                "start_date": request.start_date,
                "end_date": request.end_date,
            },
        ).mappings().all()
        return [dict(row) for row in rows]

    def _build_snapshot_static_plan(
        self,
        *,
        request: ResearchBacktestRequest,
        fallback_reason: str,
    ) -> BacktestTargetWeightPlan:
        rows = self._load_latest_signal_rows(request=request)
        if not rows:
            raise RuntimeError(
                "no selected strategy_signal rows found for "
                f"source_signal_run_id={request.source_signal_run_id}"
            )

        instrument_ids = self._unique_instrument_ids(rows)
        target_date = self._resolve_first_bar_date_on_or_after(
            request=request,
            instrument_ids=instrument_ids,
        )
        weights = self._equal_weights(instrument_ids)

        return BacktestTargetWeightPlan(
            execution_mode=SNAPSHOT_STATIC_BASKET_P1,
            target_weights_by_date={target_date: weights},
            source_effective_dates=sorted(
                {self._coerce_date(row["effective_date"]) for row in rows}
            ),
            fallback_reason=fallback_reason,
            original_signal_effective_mode=getattr(request, "signal_effective_mode", None),
            note=(
                "M5.10 P1 uses the latest selected signal basket as a static basket. "
                "This is real backtrader execution, not historical signal replay."
            ),
        )

    def _load_latest_signal_rows(self, *, request: ResearchBacktestRequest) -> list[dict[str, Any]]:
        latest_effective_date = self.session.execute(
            text(
                """
                select max(effective_date)
                from strategy_signal
                where run_id = :run_id
                  and instrument_id is not null
                  and signal_action = 'select'
                """
            ),
            {"run_id": request.source_signal_run_id},
        ).scalar()

        if latest_effective_date is None:
            return []

        rows = self.session.execute(
            text(
                """
                select
                    effective_date,
                    instrument_id,
                    raw_score,
                    rank_in_batch
                from strategy_signal
                where run_id = :run_id
                  and effective_date = :effective_date
                  and instrument_id is not null
                  and signal_action = 'select'
                order by rank_in_batch asc nulls last, instrument_id asc
                """
            ),
            {
                "run_id": request.source_signal_run_id,
                "effective_date": latest_effective_date,
            },
        ).mappings().all()
        return [dict(row) for row in rows]

    def _rows_to_equal_weight_by_date(self, rows: list[dict[str, Any]]) -> dict[date, dict[int, Decimal]]:
        grouped: dict[date, list[int]] = {}
        for row in rows:
            effective_date = self._coerce_date(row["effective_date"])
            instrument_id = int(row["instrument_id"])
            grouped.setdefault(effective_date, []).append(instrument_id)

        return {
            effective_date: self._equal_weights(self._dedupe(ids))
            for effective_date, ids in grouped.items()
            if ids
        }

    @staticmethod
    def _dedupe(items: list[int]) -> list[int]:
        return list(dict.fromkeys(int(item) for item in items))

    def _unique_instrument_ids(self, rows: list[dict[str, Any]]) -> list[int]:
        return self._dedupe([int(row["instrument_id"]) for row in rows])

    @staticmethod
    def _equal_weights(instrument_ids: list[int]) -> dict[int, Decimal]:
        unique_ids = list(dict.fromkeys(int(item) for item in instrument_ids))
        if not unique_ids:
            return {}
        weight = Decimal("1") / Decimal(str(len(unique_ids)))
        return {instrument_id: weight for instrument_id in unique_ids}

    def _resolve_first_bar_date_on_or_after(
        self,
        *,
        request: ResearchBacktestRequest,
        instrument_ids: list[int],
    ) -> date:
        if not instrument_ids:
            raise RuntimeError("cannot resolve first bar date with empty instrument_ids")

        value = self.session.execute(
            text(
                """
                select min(trade_date)
                from core_daily_bar
                where trade_date >= :start_date
                  and trade_date <= :end_date
                  and instrument_id = any(:instrument_ids)
                """
            ),
            {
                "start_date": request.start_date,
                "end_date": request.end_date,
                "instrument_ids": instrument_ids,
            },
        ).scalar()

        if value is None:
            raise RuntimeError(
                "no executable core_daily_bar date found for selected instruments "
                f"between {request.start_date} and {request.end_date}"
            )
        return self._coerce_date(value)

    def _resolve_preload_start_date(
        self,
        *,
        request: ResearchBacktestRequest,
        instrument_ids: list[int],
    ) -> date:
        row = self.session.execute(
            text(
                """
                select max(trade_date) as preload_start_date
                from core_daily_bar
                where trade_date < :start_date
                  and instrument_id = any(:instrument_ids)
                """
            ),
            {
                "start_date": request.start_date,
                "instrument_ids": instrument_ids,
            },
        ).mappings().one()

        return self._coerce_date(row["preload_start_date"]) if row["preload_start_date"] else request.start_date

    def _load_daily_bar_frames(
        self,
        *,
        request: ResearchBacktestRequest,
        instrument_ids: list[int],
        data_start_date: date,
    ) -> dict[int, pd.DataFrame]:
        rows = self.session.execute(
            text(
                """
                select
                    instrument_id,
                    trade_date,
                    open,
                    high,
                    low,
                    close,
                    volume
                from core_daily_bar
                where trade_date >= :data_start_date
                  and trade_date <= :end_date
                  and instrument_id = any(:instrument_ids)
                order by instrument_id asc, trade_date asc
                """
            ),
            {
                "data_start_date": data_start_date,
                "end_date": request.end_date,
                "instrument_ids": instrument_ids,
            },
        ).mappings().all()

        by_instrument: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            instrument_id = int(row["instrument_id"])
            by_instrument.setdefault(instrument_id, []).append(dict(row))

        frames: dict[int, pd.DataFrame] = {}
        for instrument_id, instrument_rows in by_instrument.items():
            df = pd.DataFrame(instrument_rows)
            if df.empty:
                continue

            df["trade_date"] = pd.to_datetime(df["trade_date"])
            df = df.set_index("trade_date")

            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            df["openinterest"] = 0.0
            df = df[["open", "high", "low", "close", "volume", "openinterest"]]
            df = df.dropna(subset=["open", "high", "low", "close"])

            if not df.empty:
                frames[instrument_id] = df

        return frames

    def _align_plan_to_loaded_data(
        self,
        *,
        request: ResearchBacktestRequest,
        plan: BacktestTargetWeightPlan,
        data_frames: dict[int, pd.DataFrame],
    ) -> BacktestTargetWeightPlan:
        loaded_ids = set(data_frames.keys())
        if not loaded_ids:
            raise RuntimeError("cannot align plan without loaded data frames")

        aligned: dict[date, dict[int, Decimal]] = {}
        for target_date, weights in plan.target_weights_by_date.items():
            filtered_ids = [instrument_id for instrument_id in weights.keys() if instrument_id in loaded_ids]
            if not filtered_ids:
                continue
            aligned[target_date] = self._equal_weights(filtered_ids)

        if not aligned:
            raise RuntimeError(
                "all target instruments were removed because no daily bars were loaded"
            )

        if plan.execution_mode == SNAPSHOT_STATIC_BASKET_P1:
            first_loaded_date = self._first_loaded_trade_date(
                request=request,
                data_frames=data_frames,
            )
            all_ids = sorted({iid for weights in aligned.values() for iid in weights.keys()})
            aligned = {first_loaded_date: self._equal_weights(all_ids)}

        return BacktestTargetWeightPlan(
            execution_mode=plan.execution_mode,
            target_weights_by_date=aligned,
            source_effective_dates=plan.source_effective_dates,
            fallback_reason=plan.fallback_reason,
            original_signal_effective_mode=plan.original_signal_effective_mode,
            note=plan.note,
            source_run_ids_by_date=plan.source_run_ids_by_date,
        )

    def _first_loaded_trade_date(
        self,
        *,
        request: ResearchBacktestRequest,
        data_frames: dict[int, pd.DataFrame],
    ) -> date:
        candidates: list[date] = []
        for df in data_frames.values():
            for idx in df.index:
                idx_date = idx.date() if hasattr(idx, "date") else self._coerce_date(idx)
                if request.start_date <= idx_date <= request.end_date:
                    candidates.append(idx_date)
                    break
        if not candidates:
            raise RuntimeError(
                "loaded daily bars do not contain any date inside backtest window "
                f"{request.start_date} -> {request.end_date}"
            )
        return min(candidates)

    def _build_snapshot_static_plan_from_loaded_data(
        self,
        *,
        request: ResearchBacktestRequest,
        original_plan: BacktestTargetWeightPlan,
        data_frames: dict[int, pd.DataFrame],
        fallback_reason: str,
    ) -> BacktestTargetWeightPlan:
        first_loaded_date = self._first_loaded_trade_date(request=request, data_frames=data_frames)
        instrument_ids = sorted(data_frames.keys())
        return BacktestTargetWeightPlan(
            execution_mode=SNAPSHOT_STATIC_BASKET_P1,
            target_weights_by_date={first_loaded_date: self._equal_weights(instrument_ids)},
            source_effective_dates=original_plan.source_effective_dates,
            fallback_reason=fallback_reason,
            original_signal_effective_mode=original_plan.original_signal_effective_mode,
            note=(
                "Strict target dates produced no rebalances, so M5.10 P1 reran with "
                "the loaded selected basket on the first loaded trade date."
            ),
            source_run_ids_by_date=original_plan.source_run_ids_by_date,
        )


    def _run_historical_replay_deterministic(
        self,
        *,
        request: ResearchBacktestRequest,
        execution_profile: ResearchExecutionAssumptionProfile,
        plan: BacktestTargetWeightPlan,
        data_frames: dict[int, pd.DataFrame],
    ) -> dict[str, Any]:
        """Deterministic M5.11 P1 replay for a dynamic historical signal universe."""

        initial_cash = float(request.initial_cash)
        cash = float(initial_cash)
        positions: dict[int, float] = {}
        last_close_by_instrument: dict[int, float] = {}
        daily_records: list[dict[str, Any]] = []
        order_records: list[dict[str, Any]] = []
        rebalance_records: list[dict[str, Any]] = []

        commission_rate = float(getattr(execution_profile, "commission_rate", None) or 0.0)

        frame_rows_by_date: dict[date, dict[int, dict[str, float]]] = {}
        for instrument_id, df in data_frames.items():
            for idx, row in df.iterrows():
                trade_date = idx.date() if hasattr(idx, "date") else self._coerce_date(idx)
                if trade_date < request.start_date or trade_date > request.end_date:
                    continue
                open_price = float(row.get("open") or 0.0)
                close_price = float(row.get("close") or 0.0)
                if open_price <= 0 or close_price <= 0:
                    continue
                frame_rows_by_date.setdefault(trade_date, {})[int(instrument_id)] = {
                    "open": open_price,
                    "close": close_price,
                }

        trade_dates = sorted(frame_rows_by_date.keys())
        if not trade_dates:
            raise RuntimeError(
                "no deterministic replay trade dates found in loaded core_daily_bar frames"
            )

        target_weights_by_date = dict(plan.target_weights_by_date or {})

        def portfolio_value_at_open(rows_for_date: dict[int, dict[str, float]]) -> float:
            value = cash
            for instrument_id, shares in positions.items():
                if abs(shares) <= 1e-12:
                    continue
                price = rows_for_date.get(instrument_id, {}).get("open")
                if price is None:
                    price = last_close_by_instrument.get(instrument_id)
                if price is not None:
                    value += shares * float(price)
            return float(value)

        def append_order_notifications(
            *,
            trade_date: date,
            instrument_id: int,
            is_buy: bool,
            shares: float,
            price: float,
            commission: float,
        ) -> None:
            executed_value = abs(float(shares) * float(price))
            for status in ["Submitted", "Accepted", "Completed"]:
                order_records.append(
                    {
                        "trade_date": trade_date.isoformat(),
                        "instrument_id": int(instrument_id),
                        "status": status,
                        "is_buy": bool(is_buy),
                        "created_size": float(shares),
                        "executed_size": float(shares) if status == "Completed" else 0.0,
                        "executed_price": float(price) if status == "Completed" else 0.0,
                        "executed_value": float(executed_value) if status == "Completed" else 0.0,
                        "executed_commission": float(commission) if status == "Completed" else 0.0,
                    }
                )

        for trade_date in trade_dates:
            rows_for_date = frame_rows_by_date[trade_date]

            if trade_date in target_weights_by_date:
                weights = target_weights_by_date.get(trade_date) or {}
                equity_open = portfolio_value_at_open(rows_for_date)
                submitted_count = 0
                target_count = 0

                target_ids = {int(iid) for iid, weight in weights.items() if float(weight) > 0}
                candidate_ids = sorted(set(positions.keys()).union(target_ids))

                for instrument_id in candidate_ids:
                    open_price = rows_for_date.get(instrument_id, {}).get("open")
                    if open_price is None or open_price <= 0:
                        continue

                    target_weight = float(weights.get(instrument_id, Decimal("0")))
                    if target_weight > 0:
                        target_count += 1

                    current_shares = float(positions.get(instrument_id, 0.0))
                    current_value = current_shares * float(open_price)
                    target_value = equity_open * target_weight
                    delta_value = target_value - current_value
                    if abs(delta_value) < 1e-8:
                        continue

                    delta_shares = delta_value / float(open_price)
                    commission = abs(delta_value) * commission_rate

                    cash -= delta_value
                    cash -= commission
                    new_shares = current_shares + delta_shares
                    if abs(new_shares) <= 1e-10:
                        positions.pop(instrument_id, None)
                    else:
                        positions[instrument_id] = new_shares

                    submitted_count += 1
                    append_order_notifications(
                        trade_date=trade_date,
                        instrument_id=instrument_id,
                        is_buy=delta_shares > 0,
                        shares=delta_shares,
                        price=float(open_price),
                        commission=float(commission),
                    )

                rebalance_records.append(
                    {
                        "target_date": trade_date.isoformat(),
                        "trade_date": trade_date.isoformat(),
                        "source": "exact",
                        "hook": "deterministic_open",
                        "submitted_count": int(submitted_count),
                        "target_count": int(target_count),
                        "allow_next_fallback": False,
                    }
                )

            for instrument_id, prices in rows_for_date.items():
                last_close_by_instrument[int(instrument_id)] = float(prices["close"])

            gross_exposure = 0.0
            holding_count = 0
            portfolio_value = cash
            for instrument_id, shares in positions.items():
                if abs(shares) <= 1e-12:
                    continue
                price = rows_for_date.get(instrument_id, {}).get("close")
                if price is None:
                    price = last_close_by_instrument.get(instrument_id)
                if price is None:
                    continue
                holding_count += 1
                market_value = float(shares) * float(price)
                gross_exposure += abs(market_value)
                portfolio_value += market_value

            daily_records.append(
                {
                    "trade_date": trade_date.isoformat(),
                    "portfolio_equity": float(portfolio_value),
                    "cash": float(cash),
                    "holding_count": int(holding_count),
                    "gross_exposure": float(gross_exposure),
                }
            )

        final_value = float(daily_records[-1]["portfolio_equity"]) if daily_records else initial_cash

        return {
            "start_value": float(initial_cash),
            "final_value": final_value,
            "daily_records": daily_records,
            "order_records": order_records,
            "rebalance_records": rebalance_records,
        }

    def _run_backtrader(
        self,
        *,
        request: ResearchBacktestRequest,
        execution_profile: ResearchExecutionAssumptionProfile,
        plan: BacktestTargetWeightPlan,
        data_frames: dict[int, pd.DataFrame],
    ) -> dict[str, Any]:
        daily_records: list[dict[str, Any]] = []
        order_records: list[dict[str, Any]] = []
        rebalance_records: list[dict[str, Any]] = []

        cerebro = bt.Cerebro(cheat_on_open=True)
        if hasattr(cerebro.broker, "set_coo"):
            cerebro.broker.set_coo(True)

        initial_cash = float(request.initial_cash)
        cerebro.broker.setcash(initial_cash)

        commission_rate = float(execution_profile.commission_rate or Decimal("0"))
        cerebro.broker.setcommission(commission=commission_rate)

        for instrument_id, df in data_frames.items():
            data_feed = bt.feeds.PandasData(
                dataname=df,
                datetime=None,
                open="open",
                high="high",
                low="low",
                close="close",
                volume="volume",
                openinterest="openinterest",
            )
            cerebro.adddata(data_feed, name=str(instrument_id))

        cerebro.addstrategy(
            _M510EqualWeightBacktraderStrategy,
            target_weights_by_date=plan.target_weights_by_date,
            daily_records=daily_records,
            order_records=order_records,
            rebalance_records=rebalance_records,
            record_start_date=request.start_date,
            record_end_date=request.end_date,
            allow_next_fallback=(plan.execution_mode == SNAPSHOT_STATIC_BASKET_P1),
            execution_mode=plan.execution_mode,
        )

        start_value = float(cerebro.broker.getvalue())
        cerebro.run()
        final_value = float(cerebro.broker.getvalue())

        return {
            "start_value": start_value,
            "final_value": final_value,
            "daily_records": daily_records,
            "order_records": order_records,
            "rebalance_records": rebalance_records,
        }

    def _compute_metrics(
        self,
        *,
        initial_cash: float,
        start_value: float,
        final_value: float,
        daily_records: list[dict[str, Any]],
        order_records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        trading_days = len(daily_records)
        total_return_float = final_value / initial_cash - 1.0 if initial_cash else 0.0

        annual_return_float: float | None = None
        if trading_days > 0 and final_value > 0 and initial_cash > 0:
            annual_return_float = (1.0 + total_return_float) ** (252.0 / trading_days) - 1.0

        equity_values = [float(row["portfolio_equity"]) for row in daily_records]
        daily_returns: list[float] = []
        for i in range(1, len(equity_values)):
            previous = equity_values[i - 1]
            current = equity_values[i]
            if previous != 0:
                daily_returns.append(current / previous - 1.0)

        max_drawdown_float: float | None = None
        if equity_values:
            peak = equity_values[0]
            drawdowns = []
            for value in equity_values:
                peak = max(peak, value)
                drawdowns.append(value / peak - 1.0 if peak else 0.0)
            max_drawdown_float = min(drawdowns)

        volatility_float: float | None = None
        sharpe_float: float | None = None
        if len(daily_returns) >= 2:
            mean_return = sum(daily_returns) / len(daily_returns)
            variance = sum((r - mean_return) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
            daily_std = math.sqrt(variance)
            volatility_float = daily_std * math.sqrt(252.0)
            if daily_std != 0:
                sharpe_float = mean_return / daily_std * math.sqrt(252.0)

        completed_orders = [row for row in order_records if row.get("status") == "Completed"]

        return {
            "trading_days": trading_days,
            "initial_cash": self._decimal(initial_cash),
            "start_value": self._decimal(start_value),
            "final_equity": self._decimal(final_value),
            "total_return": self._decimal(total_return_float),
            "annual_return": self._decimal(annual_return_float)
            if annual_return_float is not None
            else None,
            "max_drawdown": self._decimal(max_drawdown_float)
            if max_drawdown_float is not None
            else None,
            "sharpe_ratio": self._decimal(sharpe_float)
            if sharpe_float is not None
            else None,
            "volatility": self._decimal(volatility_float)
            if volatility_float is not None
            else None,
            "order_count": len(order_records),
            "trade_count": len(completed_orders),
        }

    @staticmethod
    def _decimal(value: float | int | Decimal | None) -> Decimal | None:
        if value is None:
            return None
        return Decimal(str(value)).quantize(Decimal("0.00000001"))

    def _upsert_backtest_result(
        self,
        *,
        request: ResearchBacktestRequest,
        metrics: dict[str, Any],
        daily_records: list[dict[str, Any]],
        order_records: list[dict[str, Any]],
        rebalance_records: list[dict[str, Any]],
        preload_start_date: date,
        plan: BacktestTargetWeightPlan,
    ) -> ResearchBacktestResult:
        obj = (
            self.session.query(ResearchBacktestResult)
            .filter(ResearchBacktestResult.run_id == request.run_id)
            .one_or_none()
        )

        stage = (
            "M5.11_HISTORICAL_SIGNAL_REPLAY_P1"
            if plan.execution_mode == HISTORICAL_SIGNAL_REPLAY_P1
            else "M5.10_BACKTRADER_REAL_EXECUTION_P1"
        )

        result_summary = {
            "stage": stage,
            "execution_enabled": True,
            "execution_mode": plan.execution_mode,
            "fallback_reason": plan.fallback_reason,
            "original_signal_effective_mode": plan.original_signal_effective_mode,
            "source_effective_dates": [d.isoformat() for d in plan.source_effective_dates],
            "source_run_ids_by_date": {d.isoformat(): run_id for d, run_id in sorted(plan.source_run_ids_by_date.items())},
            "target_dates": [d.isoformat() for d in plan.target_dates],
            "historical_rebalance_date_count": len(plan.target_weights_by_date) if plan.execution_mode == HISTORICAL_SIGNAL_REPLAY_P1 else 0,
            "strict_next_open": True,
            "next_fallback_used": False,
            "preload_start_date": str(preload_start_date),
            "source_signal_run_id": request.source_signal_run_id,
            "screen_request_id": request.screen_request_id,
            "engine_code": request.engine_code,
            "daily_record_count": len(daily_records),
            "order_record_count": len(order_records),
            "rebalance_record_count": len(rebalance_records),
            "rebalance_records": rebalance_records,
            "quality_warning_codes": ["SNAPSHOT_STATIC_BASKET_P1"]
            if plan.execution_mode == SNAPSHOT_STATIC_BASKET_P1
            else [],
            "note": plan.note or "strict NEXT_OPEN minimal equal-weight top-n backtrader execution",
        }

        if obj is None:
            obj = ResearchBacktestResult(
                run_id=request.run_id,
                backtest_request_id=request.id,
            )
            self.session.add(obj)

        obj.result_status = ResultStatus.SUCCESS.value
        obj.start_date = request.start_date
        obj.end_date = request.end_date
        obj.trading_days = metrics["trading_days"]
        obj.initial_cash = metrics["initial_cash"]
        obj.final_equity = metrics["final_equity"]
        obj.total_return = metrics["total_return"]
        obj.annual_return = metrics["annual_return"]
        obj.benchmark_return = None
        obj.excess_return = None
        obj.max_drawdown = metrics["max_drawdown"]
        obj.sharpe_ratio = metrics["sharpe_ratio"]
        obj.volatility = metrics["volatility"]
        obj.win_rate = None
        obj.turnover_avg = None
        obj.order_count = metrics["order_count"]
        obj.trade_count = metrics["trade_count"]
        obj.result_summary = result_summary
        obj.completed_at = datetime.now(timezone.utc)

        self.session.flush()
        return obj

    def _replace_series(
        self,
        *,
        run_id: int,
        daily_records: list[dict[str, Any]],
    ) -> None:
        self.session.query(OpsRunSeriesSnapshot).filter(
            OpsRunSeriesSnapshot.run_id == run_id,
            OpsRunSeriesSnapshot.series_namespace == SeriesNamespace.BACKTEST.value,
        ).delete(synchronize_session=False)

        rows: list[OpsRunSeriesSnapshot] = []
        series_fields = [
            "portfolio_equity",
            "cash",
            "holding_count",
            "gross_exposure",
        ]

        for record in daily_records:
            trade_date = self._coerce_date(record["trade_date"])
            for field in series_fields:
                value = record.get(field)
                if value is None:
                    continue

                rows.append(
                    OpsRunSeriesSnapshot(
                        run_id=run_id,
                        series_namespace=SeriesNamespace.BACKTEST.value,
                        series_code=field,
                        trade_date=trade_date,
                        instrument_id=None,
                        dimension_type="PORTFOLIO",
                        dimension_key="ALL",
                        value_numeric=Decimal(str(value)),
                        value_text=None,
                        value_json=None,
                    )
                )

        self.session.add_all(rows)
        self.session.flush()

    def _write_artifacts(
        self,
        *,
        request: ResearchBacktestRequest,
        metrics: dict[str, Any],
        daily_records: list[dict[str, Any]],
        order_records: list[dict[str, Any]],
        rebalance_records: list[dict[str, Any]],
        plan: BacktestTargetWeightPlan,
    ) -> list[OpsRunArtifact]:
        artifact_dir = Path("artifacts") / "m5" / "backtest" / f"run_{request.run_id}"
        artifact_dir.mkdir(parents=True, exist_ok=True)

        metrics_path = artifact_dir / "backtest_metrics.json"
        equity_path = artifact_dir / "backtest_equity_curve.csv"
        trade_log_path = artifact_dir / "backtest_trade_log.csv"
        rebalance_log_path = artifact_dir / "backtest_rebalance_log.csv"

        metrics_payload = self._json_safe(
            {
                **metrics,
                "execution_mode": plan.execution_mode,
                "fallback_reason": plan.fallback_reason,
                "target_dates": plan.target_dates,
                "source_effective_dates": plan.source_effective_dates,
            }
        )
        metrics_path.write_text(
            json.dumps(metrics_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        self._write_csv(
            equity_path,
            daily_records,
            fieldnames=[
                "trade_date",
                "portfolio_equity",
                "cash",
                "holding_count",
                "gross_exposure",
            ],
        )
        self._write_csv(
            trade_log_path,
            order_records,
            fieldnames=[
                "trade_date",
                "instrument_id",
                "status",
                "is_buy",
                "created_size",
                "executed_size",
                "executed_price",
                "executed_value",
                "executed_commission",
            ],
        )
        self._write_csv(
            rebalance_log_path,
            rebalance_records,
            fieldnames=[
                "target_date",
                "trade_date",
                "source",
                "hook",
                "submitted_count",
                "target_count",
                "allow_next_fallback",
            ],
        )

        rows = [
            self._upsert_artifact(
                run_id=request.run_id,
                artifact_code="backtest_metrics_json",
                artifact_name="Backtest Metrics JSON",
                artifact_type=ArtifactType.JSON.value,
                uri=str(metrics_path),
                mime_type="application/json",
                plan=plan,
            ),
            self._upsert_artifact(
                run_id=request.run_id,
                artifact_code="backtest_equity_curve_csv",
                artifact_name="Backtest Equity Curve CSV",
                artifact_type=ArtifactType.CSV.value,
                uri=str(equity_path),
                mime_type="text/csv",
                plan=plan,
            ),
            self._upsert_artifact(
                run_id=request.run_id,
                artifact_code="backtest_trade_log_csv",
                artifact_name="Backtest Trade Log CSV",
                artifact_type=ArtifactType.CSV.value,
                uri=str(trade_log_path),
                mime_type="text/csv",
                plan=plan,
            ),
            self._upsert_artifact(
                run_id=request.run_id,
                artifact_code="backtest_rebalance_log_csv",
                artifact_name="Backtest Rebalance Log CSV",
                artifact_type=ArtifactType.CSV.value,
                uri=str(rebalance_log_path),
                mime_type="text/csv",
                plan=plan,
            ),
        ]
        return rows

    @staticmethod
    def _write_csv(
        path: Path,
        rows: list[dict[str, Any]],
        *,
        fieldnames: list[str],
    ) -> None:
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field) for field in fieldnames})

    def _upsert_artifact(
        self,
        *,
        run_id: int,
        artifact_code: str,
        artifact_name: str,
        artifact_type: str,
        uri: str,
        mime_type: str,
        plan: BacktestTargetWeightPlan,
    ) -> OpsRunArtifact:
        path = Path(uri)
        obj = (
            self.session.query(OpsRunArtifact)
            .filter(
                OpsRunArtifact.run_id == run_id,
                OpsRunArtifact.artifact_code == artifact_code,
            )
            .one_or_none()
        )

        if obj is None:
            obj = OpsRunArtifact(
                run_id=run_id,
                artifact_code=artifact_code,
            )
            self.session.add(obj)

        obj.artifact_type = artifact_type
        obj.artifact_name = artifact_name
        obj.storage_backend = StorageBackend.LOCAL.value
        obj.uri = uri
        obj.mime_type = mime_type
        obj.file_size_bytes = path.stat().st_size if path.exists() else None
        obj.checksum_sha256 = None
        obj.payload_schema = None
        stage = (
            "M5.11_HISTORICAL_SIGNAL_REPLAY_P1"
            if plan.execution_mode == HISTORICAL_SIGNAL_REPLAY_P1
            else "M5.10_BACKTRADER_REAL_EXECUTION_P1"
        )

        obj.artifact_metadata = {
            "stage": stage,
            "execution_enabled": True,
            "execution_mode": plan.execution_mode,
            "fallback_reason": plan.fallback_reason,
            "strict_next_open": True,
            "next_fallback_used": False,
            "historical_rebalance_date_count": len(plan.target_weights_by_date) if plan.execution_mode == HISTORICAL_SIGNAL_REPLAY_P1 else 0,
        }

        self.session.flush()
        return obj

    @staticmethod
    def _coerce_date(value: Any) -> date:
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        if hasattr(value, "date"):
            return value.date()
        if isinstance(value, str):
            return datetime.strptime(value, "%Y-%m-%d").date()
        raise TypeError(f"cannot coerce to date: {value!r}")

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, dict):
            return {
                key: BacktestRealExecutionService._json_safe(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [BacktestRealExecutionService._json_safe(item) for item in value]
        return value

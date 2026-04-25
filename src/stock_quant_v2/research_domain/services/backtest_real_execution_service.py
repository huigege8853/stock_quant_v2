from __future__ import annotations

import csv
import json
import math
from collections import Counter
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
from stock_quant_v2.research_domain.adapters.backtrader_minimal_strategy import (
    MinimalSignalSelectionStrategy,
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


class BacktestRealExecutionService:
    """M5.11 strict NEXT_OPEN 最小真实 backtrader 执行服务。

    当前支持：
    - strategy_signal selection
    - EQUAL_WEIGHT_TOP_N
    - strict NEXT_OPEN via preload + open hooks
    - no benchmark
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
        if backtest_request_id is None:
            request = self.backtest_repo.get_latest_request()
            if request is None:
                raise RuntimeError("no backtest_request found")
        else:
            request = self.backtest_repo.get_request_by_id(backtest_request_id)

        execution_profile = self._get_execution_profile(request)

        target_weights_by_date = self._build_target_weights_by_date(request)
        instrument_ids = sorted(
            {
                instrument_id
                for weights in target_weights_by_date.values()
                for instrument_id in weights.keys()
            }
        )

        if not instrument_ids:
            raise RuntimeError(
                f"no instrument_ids resolved from signal_run_id={request.source_signal_run_id}"
            )

        preload_start_date = self._resolve_preload_start_date(
            request=request,
            instrument_ids=instrument_ids,
        )

        data_frames = self._load_daily_bar_frames(
            request=request,
            instrument_ids=instrument_ids,
            data_start_date=preload_start_date,
        )

        if not data_frames:
            raise RuntimeError("no core_daily_bar data loaded for selected instruments")

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
            MinimalSignalSelectionStrategy,
            target_weights_by_date=target_weights_by_date,
            daily_records=daily_records,
            order_records=order_records,
            rebalance_records=rebalance_records,
            record_start_date=request.start_date,
            record_end_date=request.end_date,
            allow_next_fallback=False,
        )

        start_value = float(cerebro.broker.getvalue())
        cerebro.run()
        final_value = float(cerebro.broker.getvalue())

        if not rebalance_records:
            raise RuntimeError(
                "strict NEXT_OPEN failed: no rebalance_records produced. "
                "Check preload_start_date and target effective_date."
            )

        fallback_sources = [
            row for row in rebalance_records if row.get("source") == "next_fallback"
        ]
        if fallback_sources:
            raise RuntimeError(
                "strict NEXT_OPEN violated: next_fallback was used while disabled"
            )

        metrics = self._compute_metrics(
            initial_cash=initial_cash,
            start_value=start_value,
            final_value=final_value,
            daily_records=daily_records,
            order_records=order_records,
        )

        result = self._upsert_backtest_result(
            request=request,
            metrics=metrics,
            daily_records=daily_records,
            order_records=order_records,
            rebalance_records=rebalance_records,
            preload_start_date=preload_start_date,
        )

        artifact_rows = self._write_artifacts(
            request=request,
            metrics=metrics,
            daily_records=daily_records,
            order_records=order_records,
            rebalance_records=rebalance_records,
        )

        self._replace_series(
            run_id=request.run_id,
            daily_records=daily_records,
        )

        rebalance_source_counter = Counter(
            row.get("source") for row in rebalance_records
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
                "final_equity": Decimal(str(final_value)),
                "total_return": metrics["total_return"],
                "annual_return": metrics["annual_return"],
                "max_drawdown": metrics["max_drawdown"],
                "sharpe_ratio": metrics["sharpe_ratio"],
                "volatility": metrics["volatility"],
                "order_count": metrics["order_count"],
                "trade_count": metrics["trade_count"],
                "trading_days": metrics["trading_days"],
                "data_feed_count": len(data_frames),
                "signal_rebalance_date_count": len(target_weights_by_date),
                "preload_enabled": True,
                "next_fallback_used": False,
                "rebalance_record_count": len(rebalance_records),
            },
        )

        self.session.commit()

        return {
            "run_id": request.run_id,
            "backtest_request_id": request.id,
            "backtest_result_id": result.id,
            "result_status": result.result_status,
            "start_date": str(request.start_date),
            "end_date": str(request.end_date),
            "preload_start_date": str(preload_start_date),
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
            "rebalance_source_counter": dict(rebalance_source_counter),
            "next_fallback_used": False,
            "artifact_codes": [row.artifact_code for row in artifact_rows],
            "series_written": len(daily_records) * 4,
            "note": "M5.11 strict NEXT_OPEN minimal backtrader execution completed",
        }

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

    def _build_target_weights_by_date(
        self,
        request: ResearchBacktestRequest,
    ) -> dict[date, dict[int, Decimal]]:
        if request.source_signal_run_id is None:
            raise RuntimeError("source_signal_run_id is required")

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
                order by effective_date asc, rank_in_batch asc
                """
            ),
            {
                "run_id": request.source_signal_run_id,
                "start_date": request.start_date,
                "end_date": request.end_date,
            },
        ).mappings().all()

        grouped: dict[date, list[int]] = {}

        for row in rows:
            effective_date = row["effective_date"]
            instrument_id = int(row["instrument_id"])
            grouped.setdefault(effective_date, []).append(instrument_id)

        target_weights_by_date: dict[date, dict[int, Decimal]] = {}

        for effective_date, ids in grouped.items():
            unique_ids = list(dict.fromkeys(ids))
            if not unique_ids:
                continue

            weight = Decimal("1") / Decimal(str(len(unique_ids)))
            target_weights_by_date[effective_date] = {
                instrument_id: weight for instrument_id in unique_ids
            }

        return target_weights_by_date

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

        return row["preload_start_date"] or request.start_date

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
        total_return_float = (
            final_value / initial_cash - 1.0 if initial_cash else 0.0
        )

        annual_return_float: float | None = None
        if trading_days > 0 and final_value > 0 and initial_cash > 0:
            annual_return_float = (1.0 + total_return_float) ** (
                252.0 / trading_days
            ) - 1.0

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
            variance = sum((r - mean_return) ** 2 for r in daily_returns) / (
                len(daily_returns) - 1
            )
            daily_std = math.sqrt(variance)
            volatility_float = daily_std * math.sqrt(252.0)

            if daily_std != 0:
                sharpe_float = mean_return / daily_std * math.sqrt(252.0)

        completed_orders = [
            row for row in order_records if row.get("status") == "Completed"
        ]

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
    ) -> ResearchBacktestResult:
        obj = (
            self.session.query(ResearchBacktestResult)
            .filter(ResearchBacktestResult.run_id == request.run_id)
            .one_or_none()
        )

        result_summary = {
            "stage": "M5.11_STRICT_NEXT_OPEN_MINIMAL_EXECUTION",
            "execution_enabled": True,
            "strict_next_open": True,
            "next_fallback_used": False,
            "preload_start_date": str(preload_start_date),
            "source_signal_run_id": request.source_signal_run_id,
            "screen_request_id": request.screen_request_id,
            "engine_code": request.engine_code,
            "daily_record_count": len(daily_records),
            "order_record_count": len(order_records),
            "rebalance_records": rebalance_records,
            "note": "strict NEXT_OPEN minimal equal-weight top-n backtrader execution",
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
            trade_date = date.fromisoformat(record["trade_date"])
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
    ) -> list[OpsRunArtifact]:
        artifact_dir = Path("artifacts") / "m5" / "backtest" / f"run_{request.run_id}"
        artifact_dir.mkdir(parents=True, exist_ok=True)

        metrics_path = artifact_dir / "backtest_metrics.json"
        equity_path = artifact_dir / "backtest_equity_curve.csv"
        trade_log_path = artifact_dir / "backtest_trade_log.csv"
        rebalance_log_path = artifact_dir / "backtest_rebalance_log.csv"

        metrics_payload = self._json_safe(metrics)
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
                "trade_date",
                "source",
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
            ),
            self._upsert_artifact(
                run_id=request.run_id,
                artifact_code="backtest_equity_curve_csv",
                artifact_name="Backtest Equity Curve CSV",
                artifact_type=ArtifactType.CSV.value,
                uri=str(equity_path),
                mime_type="text/csv",
            ),
            self._upsert_artifact(
                run_id=request.run_id,
                artifact_code="backtest_trade_log_csv",
                artifact_name="Backtest Trade Log CSV",
                artifact_type=ArtifactType.CSV.value,
                uri=str(trade_log_path),
                mime_type="text/csv",
            ),
            self._upsert_artifact(
                run_id=request.run_id,
                artifact_code="backtest_rebalance_log_csv",
                artifact_name="Backtest Rebalance Log CSV",
                artifact_type=ArtifactType.CSV.value,
                uri=str(rebalance_log_path),
                mime_type="text/csv",
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
        obj.artifact_metadata = {
            "stage": "M5.11_STRICT_NEXT_OPEN_MINIMAL_EXECUTION",
            "execution_enabled": True,
            "strict_next_open": True,
            "next_fallback_used": False,
        }

        self.session.flush()
        return obj

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
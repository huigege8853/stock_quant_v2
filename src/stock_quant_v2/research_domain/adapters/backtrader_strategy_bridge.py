from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from stock_quant_v2.db.models.research import ResearchBacktestRequest


class BacktraderStrategyBridge:
    """把平台 strategy_signal 转成 backtrader 可消费的策略输入计划。

    M5.6 只生成 plan，不启动 backtrader。
    """

    def __init__(self, session: Session):
        self.session = session

    def _columns(self, table_name: str) -> set[str]:
        rows = self.session.execute(
            text(
                """
                select column_name
                from information_schema.columns
                where table_schema = 'public'
                  and table_name = :table_name
                """
            ),
            {"table_name": table_name},
        ).scalars().all()

        if not rows:
            raise RuntimeError(f"table not found or has no columns: {table_name}")

        return set(rows)

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if isinstance(value, Decimal):
            return str(value)
        if hasattr(value, "isoformat"):
            return value.isoformat()
        if isinstance(value, dict):
            return {k: BacktraderStrategyBridge._json_safe(v) for k, v in value.items()}
        if isinstance(value, list):
            return [BacktraderStrategyBridge._json_safe(v) for v in value]
        return value

    def build_strategy_plan(
        self,
        *,
        request: ResearchBacktestRequest,
    ) -> dict[str, Any]:
        if request.source_signal_run_id is None:
            raise RuntimeError(
                "backtest_request.source_signal_run_id is required for M5.6 plan"
            )

        sig_cols = self._columns("strategy_signal")

        order_col = "rank_in_batch" if "rank_in_batch" in sig_cols else None
        score_col = "raw_score" if "raw_score" in sig_cols else None

        order_clause = (
            f"order by {order_col} asc"
            if order_col
            else f"order by {score_col} desc nulls last"
            if score_col
            else "order by id asc"
        )

        rows = self.session.execute(
            text(
                f"""
                select
                    id,
                    run_id,
                    strategy_version_id,
                    as_of_date,
                    effective_date,
                    instrument_id,
                    subject_type,
                    subject_key,
                    signal_role,
                    signal_side,
                    signal_action,
                    raw_score,
                    normalized_score,
                    confidence_score,
                    rank_in_batch,
                    universe_size,
                    reason_code,
                    reason_payload_json,
                    parameter_payload_json
                from strategy_signal
                where run_id = :run_id
                  and effective_date >= :start_date
                  and effective_date <= :end_date
                {order_clause}
                """
            ),
            {
                "run_id": request.source_signal_run_id,
                "start_date": request.start_date,
                "end_date": request.end_date,
            },
        ).mappings().all()

        signal_rows = [self._json_safe(dict(row)) for row in rows]
        instrument_ids = [
            int(row["instrument_id"])
            for row in rows
            if row["instrument_id"] is not None
        ]

        selected_count = len(signal_rows)
        equal_weight = (
            Decimal("1") / Decimal(str(selected_count))
            if selected_count > 0
            else None
        )

        target_rows = []
        for row in signal_rows:
            target_rows.append(
                {
                    "instrument_id": row["instrument_id"],
                    "effective_date": row["effective_date"],
                    "signal_action": row["signal_action"],
                    "raw_score": row["raw_score"],
                    "rank_in_batch": row["rank_in_batch"],
                    "target_weight_preview": str(equal_weight)
                    if equal_weight is not None
                    else None,
                }
            )

        return {
            "bridge": "BacktraderStrategyBridge",
            "execution_enabled": False,
            "source_signal_run_id": request.source_signal_run_id,
            "screen_request_id": request.screen_request_id,
            "portfolio_construction_mode": request.portfolio_construction_mode,
            "portfolio_construction_payload": request.portfolio_construction_payload,
            "selected_count": selected_count,
            "instrument_count": len(set(instrument_ids)),
            "instrument_ids": sorted(set(instrument_ids)),
            "target_preview": target_rows,
            "note": "M5.6 plan only; target_weight_preview is not M6 target_position",
        }
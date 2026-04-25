from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from stock_quant_v2.db.models.strategy.strategy_signal import StrategySignal


class SignalPublishService:
    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _as_decimal(value: float | int | None) -> Decimal | None:
        if value is None:
            return None
        return Decimal(str(value)).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)

    def build_alpha_selection_signal_rows(
        self,
        *,
        run_id: int,
        strategy_version_id: int,
        as_of_date: date,
        effective_date: date,
        selected_df,
        feature_set_code: str,
        feature_set_version: str,
        runtime_params: dict,
    ) -> list[StrategySignal]:
        published_at = self._utcnow()
        rows: list[StrategySignal] = []

        for _, row in selected_df.iterrows():
            instrument_id = int(row["instrument_id"])
            rows.append(
                StrategySignal(
                    run_id=run_id,
                    strategy_version_id=strategy_version_id,
                    as_of_date=as_of_date,
                    effective_date=effective_date,
                    subject_type="instrument",
                    subject_key=f"instrument:{instrument_id}",
                    instrument_id=instrument_id,
                    signal_role="selection",
                    signal_side="long",
                    signal_action="select",
                    raw_score=self._as_decimal(float(row["raw_score"])),
                    normalized_score=self._as_decimal(float(row["normalized_score"])),
                    confidence_score=self._as_decimal(float(row["confidence_score"])),
                    rank_in_batch=int(row["rank_in_batch"]),
                    universe_size=int(row["universe_size"]),
                    reason_code="TOP_N_SELECTED",
                    reason_payload_json={
                        "feature_set_code": feature_set_code,
                        "feature_set_version": feature_set_version,
                        "score_components": {
                            "mom_pct": round(float(row["mom_pct"]), 8),
                            "trend_pct": round(float(row["trend_pct"]), 8),
                            "low_vol_pct": round(float(row["low_vol_pct"]), 8),
                            "tradability_pct": round(float(row["tradability_pct"]), 8),
                        },
                    },
                    parameter_payload_json=runtime_params,
                    published_at=published_at,
                    created_at=published_at,
                )
            )
        return rows
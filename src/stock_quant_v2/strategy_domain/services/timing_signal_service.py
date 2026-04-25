from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from stock_quant_v2.db.models.strategy.strategy_signal import StrategySignal


class TimingSignalService:
    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _as_decimal(value: float | int | None) -> Decimal | None:
        if value is None:
            return None
        return Decimal(str(value)).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)

    def build_market_timing_signal_row(
        self,
        *,
        run_id: int,
        strategy_version_id: int,
        as_of_date: date,
        effective_date: date,
        state_score: float,
        threshold: float,
        market_state_payload: dict,
        runtime_params: dict,
        market_subject_key: str,
    ) -> StrategySignal:
        is_risk_on = float(state_score) >= float(threshold)
        published_at = self._utcnow()

        return StrategySignal(
            run_id=run_id,
            strategy_version_id=strategy_version_id,
            as_of_date=as_of_date,
            effective_date=effective_date,
            subject_type="market",
            subject_key=market_subject_key,
            instrument_id=None,
            signal_role="timing",
            signal_side="na",
            signal_action="risk_on" if is_risk_on else "risk_off",
            raw_score=self._as_decimal(float(state_score)),
            normalized_score=self._as_decimal(float(state_score)),
            confidence_score=self._as_decimal(abs(float(state_score) - float(threshold))),
            rank_in_batch=None,
            universe_size=1,
            reason_code="MARKET_RISK_ON" if is_risk_on else "MARKET_RISK_OFF",
            reason_payload_json={
                "market_state_payload": market_state_payload,
                "decision_threshold": threshold,
            },
            parameter_payload_json=runtime_params,
            published_at=published_at,
            created_at=published_at,
        )
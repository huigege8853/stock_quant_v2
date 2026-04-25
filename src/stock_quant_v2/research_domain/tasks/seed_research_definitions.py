from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_quant_v2.db.models.research import ResearchExecutionAssumptionProfile
from stock_quant_v2.research_domain.constants import DEFAULT_EXECUTION_ASSUMPTION


def _build_assumption_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(row)

    # Decimal 不能直接安全 JSON 序列化，payload 中转成 str。
    for key in (
        "commission_rate",
        "min_commission",
        "stamp_duty_rate",
        "transfer_fee_rate",
        "slippage_bps",
    ):
        if payload.get(key) is not None:
            payload[key] = str(payload[key])

    return payload


def seed_default_execution_assumption_profile(
    session: Session,
    *,
    commit: bool = False,
) -> ResearchExecutionAssumptionProfile:
    row = deepcopy(DEFAULT_EXECUTION_ASSUMPTION)
    assumption_payload = _build_assumption_payload(row)

    stmt = select(ResearchExecutionAssumptionProfile).where(
        ResearchExecutionAssumptionProfile.profile_code == row["profile_code"],
        ResearchExecutionAssumptionProfile.version_code == row["version_code"],
    )
    obj = session.execute(stmt).scalar_one_or_none()

    if obj is None:
        obj = ResearchExecutionAssumptionProfile(
            profile_code=row["profile_code"],
            version_code=row["version_code"],
            profile_name=row["profile_name"],
            market_code=row["market_code"],
            asset_class=row["asset_class"],
            frequency=row["frequency"],
            commission_model=row["commission_model"],
            commission_rate=row["commission_rate"],
            min_commission=row["min_commission"],
            stamp_duty_rate=row["stamp_duty_rate"],
            transfer_fee_rate=row["transfer_fee_rate"],
            slippage_model=row["slippage_model"],
            slippage_bps=row["slippage_bps"],
            price_fill_rule=row["price_fill_rule"],
            volume_fill_rule=row["volume_fill_rule"],
            t_plus_rule=row["t_plus_rule"],
            lot_size=row["lot_size"],
            allow_fractional_share=row["allow_fractional_share"],
            limit_up_down_rule=row["limit_up_down_rule"],
            suspend_rule=row["suspend_rule"],
            cash_rule=row["cash_rule"],
            assumption_payload=assumption_payload,
            is_active=row["is_active"],
        )
        session.add(obj)
    else:
        obj.profile_name = row["profile_name"]
        obj.market_code = row["market_code"]
        obj.asset_class = row["asset_class"]
        obj.frequency = row["frequency"]
        obj.commission_model = row["commission_model"]
        obj.commission_rate = row["commission_rate"]
        obj.min_commission = row["min_commission"]
        obj.stamp_duty_rate = row["stamp_duty_rate"]
        obj.transfer_fee_rate = row["transfer_fee_rate"]
        obj.slippage_model = row["slippage_model"]
        obj.slippage_bps = row["slippage_bps"]
        obj.price_fill_rule = row["price_fill_rule"]
        obj.volume_fill_rule = row["volume_fill_rule"]
        obj.t_plus_rule = row["t_plus_rule"]
        obj.lot_size = row["lot_size"]
        obj.allow_fractional_share = row["allow_fractional_share"]
        obj.limit_up_down_rule = row["limit_up_down_rule"]
        obj.suspend_rule = row["suspend_rule"]
        obj.cash_rule = row["cash_rule"]
        obj.assumption_payload = assumption_payload
        obj.is_active = row["is_active"]

    session.flush()

    if commit:
        session.commit()

    return obj


def seed_research_definitions(
    session: Session,
    *,
    commit: bool = False,
) -> dict[str, Any]:
    profile = seed_default_execution_assumption_profile(session, commit=False)

    if commit:
        session.commit()

    return {
        "execution_assumption_profile": {
            "id": profile.id,
            "profile_code": profile.profile_code,
            "version_code": profile.version_code,
            "profile_name": profile.profile_name,
        },
        "benchmark_definition": {
            "seeded": False,
            "reason": "default benchmark is intentionally not configured in M5.2",
        },
    }
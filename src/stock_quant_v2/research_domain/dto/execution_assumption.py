from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class ExecutionAssumptionProfileDTO:
    profile_code: str
    version_code: str
    profile_name: str

    market_code: str
    asset_class: str
    frequency: str

    commission_model: str | None = None
    commission_rate: Decimal | None = None
    min_commission: Decimal | None = None
    stamp_duty_rate: Decimal | None = None
    transfer_fee_rate: Decimal | None = None

    slippage_model: str | None = None
    slippage_bps: Decimal | None = None

    price_fill_rule: str | None = None
    volume_fill_rule: str | None = None
    t_plus_rule: str | None = None
    lot_size: int | None = None
    allow_fractional_share: bool = False

    limit_up_down_rule: str | None = None
    suspend_rule: str | None = None
    cash_rule: str | None = None

    assumption_payload: dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
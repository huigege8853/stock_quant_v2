from __future__ import annotations

import json
import os
from datetime import date
from decimal import Decimal
from typing import Any

from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.trading_domain.services.paper_trading_orchestrator import (
    PaperTradingDailyPlan,
)
from stock_quant_v2.trading_domain.tasks.run_paper_trading_date_range import (
    run_paper_trading_date_range,
)


def _env_required(name: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise RuntimeError(f"缺少环境变量: {name}")
    return value.strip()


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_date(value: str | None) -> date | None:
    if value is None or str(value).strip() == "":
        return None
    return date.fromisoformat(str(value).strip())


def _parse_decimal(value: Any, default: str) -> Decimal:
    if value is None or str(value).strip() == "":
        return Decimal(default)
    return Decimal(str(value).strip())


def _parse_int(value: Any, *, default: int | None = None) -> int:
    if value is None or str(value).strip() == "":
        if default is None:
            raise RuntimeError("缺少必填 run_id / id 字段")
        return default
    return int(str(value).strip())


def _build_daily_plan(item: dict[str, Any]) -> PaperTradingDailyPlan:
    return PaperTradingDailyPlan(
        portfolio_id=_parse_int(item.get("portfolio_id")),
        as_of_date=_parse_date(item.get("as_of_date")) or _parse_date(item.get("effective_date")),
        effective_date=_parse_date(item.get("effective_date")),
        source_position_run_id=_parse_int(item.get("source_position_run_id"), default=0),
        carry_position_run_id=_parse_int(item.get("carry_position_run_id")),
        target_position_run_id=_parse_int(item.get("target_position_run_id")),
        order_run_id=_parse_int(item.get("order_run_id")),
        fill_run_id=_parse_int(item.get("fill_run_id")),
        position_run_id=_parse_int(item.get("position_run_id")),
        previous_snapshot_run_id=_parse_int(item.get("previous_snapshot_run_id"), default=0),
        snapshot_run_id=_parse_int(item.get("snapshot_run_id")),
        source_effective_date=_parse_date(item.get("source_effective_date")),
        template_order_run_id=(
            _parse_int(item.get("template_order_run_id"))
            if item.get("template_order_run_id") not in (None, "")
            else None
        ),
        target_quantity_source=str(item.get("target_quantity_source") or "AUTO"),
        replace_existing=bool(item.get("replace_existing", _env_bool("M7_REPLACE_EXISTING", False))),
        write_hold_orders=bool(item.get("write_hold_orders", False)),
        keep_closed_positions=bool(item.get("keep_closed_positions", True)),
        commission_rate=_parse_decimal(item.get("commission_rate"), "0.0003"),
        min_commission=_parse_decimal(item.get("min_commission"), "5"),
        stamp_duty_rate=_parse_decimal(item.get("stamp_duty_rate"), "0.001"),
        slippage_rate=_parse_decimal(item.get("slippage_rate"), "0"),
    )


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    return value


def _load_daily_plans_json() -> str:
    file_path = os.getenv("M7_DAILY_PLANS_FILE")
    if file_path and file_path.strip():
        with open(file_path.strip(), "r", encoding="utf-8") as f:
            return f.read()
    return _env_required("M7_DAILY_PLANS_JSON")


def main() -> None:
    raw = _load_daily_plans_json()
    items = json.loads(raw)
    if not isinstance(items, list):
        raise RuntimeError("M7_DAILY_PLANS_JSON 必须是 JSON 数组")

    daily_plans = [_build_daily_plan(item) for item in items]
    session = SessionLocal()
    try:
        result = run_paper_trading_date_range(
            session=session,
            daily_plans=daily_plans,
            chain_previous_outputs=_env_bool("M7_CHAIN_PREVIOUS_OUTPUTS", True),
            stop_on_error=_env_bool("M7_STOP_ON_ERROR", True),
        )
        session.commit()
        print(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
import os
from datetime import date
from decimal import Decimal
from typing import Any

from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.trading_domain.tasks.run_paper_trading_daily import (
    run_paper_trading_daily,
)


def _env_required(name: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise RuntimeError(f"缺少环境变量: {name}")
    return value.strip()


def _env_int(name: str) -> int:
    return int(_env_required(name))


def _env_optional_int(name: str) -> int | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return None
    return int(value.strip())


def _env_date(name: str) -> date:
    return date.fromisoformat(_env_required(name))


def _env_optional_date(name: str) -> date | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return None
    return date.fromisoformat(value.strip())


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_decimal(name: str, default: str) -> Decimal:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return Decimal(default)
    return Decimal(value.strip())


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    return value


def main() -> None:
    session = SessionLocal()
    try:
        result = run_paper_trading_daily(
            session=session,
            portfolio_id=_env_int("M7_PORTFOLIO_ID"),
            as_of_date=_env_date("M7_AS_OF_DATE"),
            effective_date=_env_date("M7_EFFECTIVE_DATE"),
            source_position_run_id=_env_int("M7_SOURCE_POSITION_RUN_ID"),
            carry_position_run_id=_env_int("M7_CARRY_POSITION_RUN_ID"),
            target_position_run_id=_env_int("M7_TARGET_POSITION_RUN_ID"),
            order_run_id=_env_int("M7_ORDER_RUN_ID"),
            fill_run_id=_env_int("M7_FILL_RUN_ID"),
            position_run_id=_env_int("M7_POSITION_RUN_ID"),
            previous_snapshot_run_id=_env_int("M7_PREVIOUS_SNAPSHOT_RUN_ID"),
            snapshot_run_id=_env_int("M7_SNAPSHOT_RUN_ID"),
            source_effective_date=_env_optional_date("M7_SOURCE_EFFECTIVE_DATE"),
            template_order_run_id=_env_optional_int("M7_TEMPLATE_ORDER_RUN_ID"),
            target_quantity_source=os.getenv("M7_TARGET_QUANTITY_SOURCE", "AUTO"),
            replace_existing=_env_bool("M7_REPLACE_EXISTING", False),
            write_hold_orders=_env_bool("M7_WRITE_HOLD_ORDERS", False),
            keep_closed_positions=_env_bool("M7_KEEP_CLOSED_POSITIONS", True),
            commission_rate=_env_decimal("M7_COMMISSION_RATE", "0.0003"),
            min_commission=_env_decimal("M7_MIN_COMMISSION", "5"),
            stamp_duty_rate=_env_decimal("M7_STAMP_DUTY_RATE", "0.001"),
            slippage_rate=_env_decimal("M7_SLIPPAGE_RATE", "0"),
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

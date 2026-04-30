from __future__ import annotations

import argparse
import json
import os
import uuid
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.trading_domain.tasks.build_target_positions import (
    BuildTargetPositionsTaskRequest,
    build_target_positions,
)
from stock_quant_v2.trading_domain.tasks.run_paper_trading_daily import (
    run_paper_trading_daily,
)

from stock_quant_v2.trading_domain.constants import (
    DEFAULT_PORTFOLIO_CONSTRUCTION_MODE,
    DEFAULT_TARGET_COUNT,
)


def _env_int(name: str, default: int | None = None) -> int | None:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def _env_date(name: str, default: str | None = None) -> date | None:
    raw = os.getenv(name) or default
    if not raw:
        return None
    return date.fromisoformat(raw)


def _env_decimal(name: str, default: str | None = None) -> Decimal | None:
    raw = os.getenv(name) or default
    if raw is None or raw == "":
        return None
    return Decimal(str(raw))


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _get_columns(session: Session, table_name: str) -> set[str]:
    rows = session.execute(
        text(
            """
            select column_name
            from information_schema.columns
            where table_schema = 'public'
              and table_name = :table_name
            """
        ),
        {"table_name": table_name},
    ).all()
    return {r[0] for r in rows}


def _create_ops_run(
    session: Session,
    *,
    run_type: str,
    run_name: str,
    context: dict[str, Any],
    status: str = "RUNNING",
) -> int:
    cols = _get_columns(session, "ops_run")
    payload: dict[str, Any] = {}

    if "run_uid" in cols:
        payload["run_uid"] = str(uuid.uuid4())
    if "run_type" in cols:
        payload["run_type"] = run_type[:32]
    if "run_name" in cols:
        payload["run_name"] = run_name
    if "status" in cols:
        payload["status"] = status
    if "trigger_type" in cols:
        payload["trigger_type"] = "MANUAL"
    if "requested_at" in cols:
        payload["requested_at"] = "__NOW__"
    if "started_at" in cols:
        payload["started_at"] = "__NOW__"
    if "created_at" in cols:
        payload["created_at"] = "__NOW__"
    if "updated_at" in cols:
        payload["updated_at"] = "__NOW__"
    if "context_json" in cols:
        payload["context_json"] = json.dumps(context, ensure_ascii=False)

    insert_cols = list(payload.keys())
    value_sql: list[str] = []
    params: dict[str, Any] = {}

    for c in insert_cols:
        if payload[c] == "__NOW__":
            value_sql.append("now()")
        elif c == "context_json":
            value_sql.append("cast(:context_json as jsonb)")
            params[c] = payload[c]
        else:
            value_sql.append(f":{c}")
            params[c] = payload[c]

    return int(
        session.execute(
            text(
                f"""
                insert into ops_run ({", ".join(insert_cols)})
                values ({", ".join(value_sql)})
                returning id
                """
            ),
            params,
        ).scalar_one()
    )


def _mark_success(session: Session, run_id: int) -> None:
    cols = _get_columns(session, "ops_run")
    assignments = []
    if "status" in cols:
        assignments.append("status = 'SUCCESS'")
    if "ended_at" in cols:
        assignments.append("ended_at = now()")
    if "updated_at" in cols:
        assignments.append("updated_at = now()")
    if assignments:
        session.execute(
            text(f"update ops_run set {', '.join(assignments)} where id = :run_id"),
            {"run_id": run_id},
        )


def _mark_failed(session: Session, run_id: int, exc: Exception) -> None:
    cols = _get_columns(session, "ops_run")
    assignments = []
    params = {"run_id": run_id, "error_message": str(exc)[:1000]}
    if "status" in cols:
        assignments.append("status = 'FAILED'")
    if "error_message" in cols:
        assignments.append("error_message = :error_message")
    if "ended_at" in cols:
        assignments.append("ended_at = now()")
    if "updated_at" in cols:
        assignments.append("updated_at = now()")
    if assignments:
        session.execute(
            text(f"update ops_run set {', '.join(assignments)} where id = :run_id"),
            params,
        )


def _resolve_portfolio_id(session: Session, explicit_portfolio_id: int | None) -> int:
    if explicit_portfolio_id is not None:
        exists = session.execute(
            text("select 1 from trading_paper_portfolio where id = :id"),
            {"id": explicit_portfolio_id},
        ).scalar_one_or_none()
        if exists is None:
            raise RuntimeError(f"portfolio_id does not exist: {explicit_portfolio_id}")
        return explicit_portfolio_id

    portfolio_code = os.getenv("M7_PORTFOLIO_CODE", "paper_alpha_selection_v1_default")
    value = session.execute(
        text(
            """
            select id
            from trading_paper_portfolio
            where portfolio_code = :portfolio_code
            order by id desc
            limit 1
            """
        ),
        {"portfolio_code": portfolio_code},
    ).scalar_one_or_none()

    if value is None:
        raise RuntimeError(f"portfolio_code not found: {portfolio_code}")

    return int(value)


def _resolve_latest_available_bar_date(session: Session) -> date:
    value = session.execute(
        text("select max(trade_date) from core_daily_bar")
    ).scalar_one_or_none()
    if value is None:
        raise RuntimeError("core_daily_bar is empty; cannot resolve latest available bar date")
    return value


def _resolve_previous_snapshot(session: Session, portfolio_id: int, effective_date: date) -> dict[str, Any] | None:
    rows = session.execute(
        text(
            """
            select
                run_id,
                snapshot_date,
                cash_balance,
                total_equity
            from trading_paper_portfolio_snapshot
            where portfolio_id = :portfolio_id
              and snapshot_date < :effective_date
            order by snapshot_date desc, run_id desc
            limit 1
            """
        ),
        {
            "portfolio_id": portfolio_id,
            "effective_date": effective_date,
        },
    ).mappings().all()

    if not rows:
        return None

    return dict(rows[0])


def _pick_position_date_column(session: Session) -> str | None:
    cols = _get_columns(session, "trading_paper_position")
    for candidate in ("effective_date", "as_of_date", "position_date", "trade_date"):
        if candidate in cols:
            return candidate
    return None


def _resolve_previous_position(session: Session, portfolio_id: int, effective_date: date) -> dict[str, Any] | None:
    date_col = _pick_position_date_column(session)

    if date_col is not None:
        rows = session.execute(
            text(
                f"""
                select
                    run_id,
                    {date_col} as source_effective_date
                from trading_paper_position
                where portfolio_id = :portfolio_id
                  and {date_col} < :effective_date
                group by run_id, {date_col}
                order by {date_col} desc, run_id desc
                limit 1
                """
            ),
            {
                "portfolio_id": portfolio_id,
                "effective_date": effective_date,
            },
        ).mappings().all()

        if rows:
            return dict(rows[0])

    # fallback：如果 position 表没有明确日期列，就退化为只取最近一个 run_id
    rows = session.execute(
        text(
            """
            select
                run_id
            from trading_paper_position
            where portfolio_id = :portfolio_id
            group by run_id
            order by run_id desc
            limit 1
            """
        ),
        {
            "portfolio_id": portfolio_id,
        },
    ).mappings().all()

    if not rows:
        return None

    row = dict(rows[0])
    row["source_effective_date"] = None
    return row


def _resolve_latest_signal_run(
    session: Session,
    *,
    effective_date: date,
    explicit_signal_run_id: int | None,
    explicit_as_of_date: date | None,
) -> tuple[int, date, date]:
    if explicit_signal_run_id is not None:
        row = session.execute(
            text(
                """
                select
                    run_id,
                    max(as_of_date) as as_of_date,
                    max(effective_date) as effective_date
                from strategy_signal
                where run_id = :run_id
                group by run_id
                """
            ),
            {"run_id": explicit_signal_run_id},
        ).mappings().one_or_none()

        if row is None:
            raise RuntimeError(f"source_signal_run_id not found: {explicit_signal_run_id}")

        resolved_as_of = explicit_as_of_date or row["as_of_date"]
        resolved_effective = row["effective_date"]
        if resolved_as_of is None:
            raise RuntimeError(f"cannot resolve as_of_date for signal run {explicit_signal_run_id}")
        if resolved_effective is None:
            raise RuntimeError(f"cannot resolve effective_date for signal run {explicit_signal_run_id}")
        if resolved_effective > effective_date:
            raise RuntimeError(
                "M7 daily refresh refuses future signal: "
                f"signal_effective_date={resolved_effective}, paper_execution_date={effective_date}"
            )
        return int(row["run_id"]), resolved_as_of, resolved_effective

    row = session.execute(
        text(
            """
            select
                run_id,
                max(as_of_date) as as_of_date,
                max(effective_date) as effective_date
            from strategy_signal
            where effective_date <= :effective_date
            group by run_id
            order by max(effective_date) desc, run_id desc
            limit 1
            """
        ),
        {"effective_date": effective_date},
    ).mappings().one_or_none()

    if row is None:
        raise RuntimeError("cannot resolve latest strategy_signal run for M7 daily refresh")

    return int(row["run_id"]), row["as_of_date"], row["effective_date"]


def _resolve_latest_screen_request_id(
    session: Session,
    *,
    effective_date: date,
    source_signal_run_id: int | None,
    explicit_screen_request_id: int | None,
) -> int | None:
    if explicit_screen_request_id is not None:
        return explicit_screen_request_id

    cols = _get_columns(session, "research_screen_result")
    req_col = None
    if "request_id" in cols:
        req_col = "request_id"
    elif "screen_request_id" in cols:
        req_col = "screen_request_id"

    if req_col is None:
        return None

    status_col = None
    if "result_status" in cols:
        status_col = "result_status"
    elif "status" in cols:
        status_col = "status"

    where_status = ""
    if status_col is not None:
        where_status = f" and {status_col} = 'SUCCESS'"

    # Prefer a screen result produced from the same signal run when the schema supports it.
    # This prevents date-only resolution from accidentally pairing an old/new screen with
    # a different strategy_signal run on the same effective date.
    signal_run_col = None
    if "source_signal_run_id" in cols:
        signal_run_col = "source_signal_run_id"
    elif "signal_run_id" in cols:
        signal_run_col = "signal_run_id"

    if source_signal_run_id is not None and signal_run_col is not None:
        row = session.execute(
            text(
                f"""
                select {req_col} as request_id
                from research_screen_result
                where {signal_run_col} = :source_signal_run_id
                  and effective_date <= :effective_date
                  {where_status}
                order by effective_date desc, {req_col} desc
                limit 1
                """
            ),
            {
                "source_signal_run_id": source_signal_run_id,
                "effective_date": effective_date,
            },
        ).mappings().one_or_none()
        if row is not None:
            return int(row["request_id"])

    row = session.execute(
        text(
            f"""
            select {req_col} as request_id
            from research_screen_result
            where effective_date <= :effective_date
              {where_status}
            order by effective_date desc, {req_col} desc
            limit 1
            """
        ),
        {"effective_date": effective_date},
    ).mappings().one_or_none()

    if row is None:
        return None

    return int(row["request_id"])


def _build_target_positions_auto(
    session: Session,
    *,
    portfolio_id: int,
    source_signal_run_id: int,
    source_screen_request_id: int | None,
    as_of_date: date,
    effective_date: date,
) -> int:
    run_id = _create_ops_run(
        session,
        run_type="paper_target_position",
        run_name="M7 Daily Target Quantity Sizing",
        context={
            "module": "M7",
            "stage": "AUTO",
            "source_signal_run_id": source_signal_run_id,
            "source_screen_request_id": source_screen_request_id,
            "portfolio_id": portfolio_id,
            "as_of_date": as_of_date.isoformat(),
            "effective_date": effective_date.isoformat(),
        },
    )
    session.commit()

    result = build_target_positions(
        session=session,
        request=BuildTargetPositionsTaskRequest(
            run_id=run_id,
            portfolio_id=portfolio_id,
            source_signal_run_id=source_signal_run_id,
            source_screen_request_id=source_screen_request_id,
            as_of_date=as_of_date,
            effective_date=effective_date,
            construction_mode=os.getenv(
                "M7_PORTFOLIO_CONSTRUCTION_MODE",
                DEFAULT_PORTFOLIO_CONSTRUCTION_MODE,
            ),
            target_count=int(os.getenv("M7_TARGET_COUNT", str(DEFAULT_TARGET_COUNT))),
            long_only=True,
            sizing_mode=os.getenv("M7_TARGET_SIZING_MODE", "EQUAL_WEIGHT_BY_EQUITY"),
            sizing_capital=_env_decimal("M7_TARGET_SIZING_CAPITAL"),
            price_date=as_of_date,
            price_source=os.getenv("M7_TARGET_PRICE_SOURCE", "AS_OF_CLOSE"),
            lot_size=_env_decimal("M7_TARGET_LOT_SIZE", "100") or Decimal("100"),
            cash_buffer_rate=_env_decimal("M7_TARGET_CASH_BUFFER_RATE", "0") or Decimal("0"),
        ),
    )
    _mark_success(session, run_id)
    session.commit()

    print(
        json.dumps(
            {
                "module": "M7.target_quantity",
                "run_id": run_id,
                "portfolio_id": result.portfolio_id,
                "source_signal_run_id": result.source_signal_run_id,
                "source_screen_request_id": result.source_screen_request_id,
                "as_of_date": result.as_of_date.isoformat(),
                "effective_date": result.effective_date.isoformat(),
                "target_position_count": result.target_position_count,
                "target_quantity_total": str(result.target_quantity_total),
                "target_amount_total": str(result.target_amount_total),
                "zero_quantity_count": result.zero_quantity_count,
                "status": result.status,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    return run_id


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Automatic M7 daily refresh chain. "
            "This is for non-empty portfolios with an existing previous snapshot/position."
        )
    )
    parser.add_argument("--portfolio-id", type=int, default=None)
    parser.add_argument("--effective-date", default=None, help="YYYY-MM-DD; default: latest available bar date")
    parser.add_argument("--as-of-date", default=None, help="YYYY-MM-DD; default: resolved from latest signal run")
    parser.add_argument("--source-signal-run-id", type=int, default=None)
    parser.add_argument("--source-screen-request-id", type=int, default=None)
    parser.add_argument("--replace-existing", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    session = SessionLocal()

    root_run_id: int | None = None
    child_run_ids: list[int] = []

    try:
        portfolio_id = _resolve_portfolio_id(session, args.portfolio_id)
        latest_completed_bar_date = _resolve_latest_available_bar_date(session)
        effective_date = date.fromisoformat(args.effective_date) if args.effective_date else latest_completed_bar_date

        if effective_date > latest_completed_bar_date:
            raise RuntimeError(
                "M7 daily refresh refuses to execute beyond completed market data: "
                f"paper_execution_date={effective_date}, "
                f"latest_completed_core_daily_bar_date={latest_completed_bar_date}"
            )

        previous_snapshot = _resolve_previous_snapshot(session, portfolio_id, effective_date)
        if previous_snapshot is None:
            raise RuntimeError(
                f"M7 daily refresh requires previous snapshot. "
                f"portfolio_id={portfolio_id}, effective_date={effective_date}. "
                f"No previous snapshot found; use M6 first chain."
            )

        previous_position = _resolve_previous_position(session, portfolio_id, effective_date)
        if previous_position is None:
            raise RuntimeError(
                f"M7 daily refresh requires previous position run. "
                f"portfolio_id={portfolio_id}, effective_date={effective_date}. "
                f"No previous position found; use M6 first chain."
            )

        explicit_as_of_date = date.fromisoformat(args.as_of_date) if args.as_of_date else None
        source_signal_run_id, as_of_date, signal_effective_date = _resolve_latest_signal_run(
            session,
            effective_date=effective_date,
            explicit_signal_run_id=args.source_signal_run_id,
            explicit_as_of_date=explicit_as_of_date,
        )
        source_screen_request_id = _resolve_latest_screen_request_id(
            session,
            effective_date=effective_date,
            source_signal_run_id=source_signal_run_id,
            explicit_screen_request_id=args.source_screen_request_id,
        )

        signal_carry_days = (effective_date - signal_effective_date).days
        signal_usage_mode = (
            "EXACT_SIGNAL_DATE"
            if signal_effective_date == effective_date
            else "CARRY_LATEST_AVAILABLE_SIGNAL"
        )
        print(
            json.dumps(
                {
                    "module": "M7.date_alignment",
                    "date_policy": "paper_execution_date defaults to latest completed core_daily_bar date",
                    "portfolio_id": portfolio_id,
                    "latest_completed_core_daily_bar_date": latest_completed_bar_date.isoformat(),
                    "paper_execution_date": effective_date.isoformat(),
                    "target_price_date": as_of_date.isoformat(),
                    "source_signal_run_id": source_signal_run_id,
                    "source_signal_as_of_date": as_of_date.isoformat(),
                    "source_signal_effective_date": signal_effective_date.isoformat(),
                    "source_screen_request_id": source_screen_request_id,
                    "signal_resolution_policy": "latest strategy_signal effective_date <= paper_execution_date",
                    "signal_usage_mode": signal_usage_mode,
                    "signal_carry_days": signal_carry_days,
                    "screen_resolution_policy": "prefer same source_signal_run_id when research_screen_result supports it",
                    "status": "PASS",
                    "note": (
                        "exact signal date match"
                        if signal_carry_days == 0
                        else "M7 is explicitly carrying the latest available signal to the paper execution date"
                    ),
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )

        root_run_id = _create_ops_run(
            session,
            run_type="PAPER_TRADING",
            run_name="bootstrap_m7_daily_refresh_chain",
            context={
                "module": "M7",
                "stage": "AUTO",
                "portfolio_id": portfolio_id,
                "as_of_date": as_of_date.isoformat(),
                "effective_date": effective_date.isoformat(),
                "source_signal_effective_date": signal_effective_date.isoformat(),
                "latest_completed_core_daily_bar_date": latest_completed_bar_date.isoformat(),
                "date_policy": "paper_execution_date defaults to latest completed core_daily_bar date",
                "source_signal_run_id": source_signal_run_id,
                "source_screen_request_id": source_screen_request_id,
                "previous_snapshot_run_id": int(previous_snapshot["run_id"]),
                "source_position_run_id": int(previous_position["run_id"]),
                "replace_existing": bool(args.replace_existing),
            },
        )
        session.commit()

        target_position_run_id = _build_target_positions_auto(
            session=session,
            portfolio_id=portfolio_id,
            source_signal_run_id=source_signal_run_id,
            source_screen_request_id=source_screen_request_id,
            as_of_date=as_of_date,
            effective_date=effective_date,
        )

        carry_run_id = _create_ops_run(
            session,
            run_type="PAPER_TRADING",
            run_name="M7 Auto Carry Position",
            context={"module": "M7", "stage": "AUTO", "role": "carry", "effective_date": effective_date.isoformat()},
        )
        order_run_id = _create_ops_run(
            session,
            run_type="PAPER_TRADING",
            run_name="M7 Auto Rebalance Order",
            context={"module": "M7", "stage": "AUTO", "role": "order", "effective_date": effective_date.isoformat()},
        )
        fill_run_id = _create_ops_run(
            session,
            run_type="PAPER_TRADING",
            run_name="M7 Auto Rebalance Fill",
            context={"module": "M7", "stage": "AUTO", "role": "fill", "effective_date": effective_date.isoformat()},
        )
        position_run_id = _create_ops_run(
            session,
            run_type="PAPER_TRADING",
            run_name="M7 Auto Position After Fill",
            context={"module": "M7", "stage": "AUTO", "role": "position", "effective_date": effective_date.isoformat()},
        )
        snapshot_run_id = _create_ops_run(
            session,
            run_type="PAPER_TRADING",
            run_name="M7 Auto Portfolio Snapshot",
            context={"module": "M7", "stage": "AUTO", "role": "snapshot", "effective_date": effective_date.isoformat()},
        )
        child_run_ids = [carry_run_id, order_run_id, fill_run_id, position_run_id, snapshot_run_id]
        session.commit()

        result = run_paper_trading_daily(
            session=session,
            portfolio_id=portfolio_id,
            as_of_date=as_of_date,
            effective_date=effective_date,
            source_position_run_id=int(previous_position["run_id"]),
            carry_position_run_id=carry_run_id,
            target_position_run_id=target_position_run_id,
            order_run_id=order_run_id,
            fill_run_id=fill_run_id,
            position_run_id=position_run_id,
            previous_snapshot_run_id=int(previous_snapshot["run_id"]),
            snapshot_run_id=snapshot_run_id,
            source_effective_date=previous_position.get("source_effective_date"),
            template_order_run_id=None,
            target_quantity_source=os.getenv("M7_TARGET_QUANTITY_SOURCE", "AUTO"),
            replace_existing=bool(args.replace_existing),
            write_hold_orders=_env_bool("M7_WRITE_HOLD_ORDERS", False),
            keep_closed_positions=_env_bool("M7_KEEP_CLOSED_POSITIONS", True),
            commission_rate=_env_decimal("M7_COMMISSION_RATE", "0.0003") or Decimal("0.0003"),
            min_commission=_env_decimal("M7_MIN_COMMISSION", "5") or Decimal("5"),
            stamp_duty_rate=_env_decimal("M7_STAMP_DUTY_RATE", "0.001") or Decimal("0.001"),
            slippage_rate=_env_decimal("M7_SLIPPAGE_RATE", "0") or Decimal("0"),
        )

        for rid in child_run_ids:
            _mark_success(session, rid)
        if root_run_id is not None:
            _mark_success(session, root_run_id)

        session.commit()
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0

    except Exception as exc:
        session.rollback()
        try:
            if root_run_id is not None:
                _mark_failed(session, root_run_id, exc)
            for rid in child_run_ids:
                _mark_failed(session, rid, exc)
            session.commit()
        except Exception:
            session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
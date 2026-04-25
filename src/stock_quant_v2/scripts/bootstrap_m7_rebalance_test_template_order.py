from __future__ import annotations

import json
import os
from datetime import datetime
from decimal import Decimal, ROUND_FLOOR
from typing import Any

from sqlalchemy import text

from stock_quant_v2.data_domain.repositories.run_repository import RunRepository
from stock_quant_v2.db.session import SessionLocal


ORDER_TABLE = "trading_paper_order"


def _env_int(name: str, default: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        if default is None:
            raise RuntimeError(f"缺少环境变量: {name}")
        return default
    return int(raw)


def _env_decimal(name: str, default: str) -> Decimal:
    raw = os.getenv(name) or default
    return Decimal(str(raw))


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _floor_to_lot(quantity: Decimal, lot_size: Decimal) -> Decimal:
    if lot_size <= 0:
        return quantity
    lots = (quantity / lot_size).to_integral_value(rounding=ROUND_FLOOR)
    return lots * lot_size


def _get_columns(session, table_name: str) -> list[str]:
    rows = session.execute(
        text(
            """
            select column_name
            from information_schema.columns
            where table_schema = 'public'
              and table_name = :table_name
            order by ordinal_position
            """
        ),
        {"table_name": table_name},
    ).mappings().all()
    return [row["column_name"] for row in rows]


def _resolve_security_key(columns: list[str]) -> str:
    for col in [
        "instrument_id",
        "security_id",
        "ticker",
        "symbol",
        "instrument_code",
        "vendor_symbol",
    ]:
        if col in columns:
            return col
    raise RuntimeError("trading_paper_order 无法识别证券键")


def _resolve_order_quantity_col(columns: list[str]) -> str:
    for col in ["order_quantity", "quantity", "requested_quantity"]:
        if col in columns:
            return col
    raise RuntimeError("trading_paper_order 无法识别订单数量字段")


def _copy_insert_order(session, *, columns: list[str], payload: dict[str, Any]) -> None:
    insert_columns = [c for c in columns if c not in {"id", "created_id", "updated_id"}]
    insert_payload = {c: payload.get(c) for c in insert_columns}

    column_sql = ", ".join([f'"{c}"' for c in insert_columns])
    value_sql = ", ".join([f":{c}" for c in insert_columns])

    session.execute(
        text(
            f"""
            insert into {ORDER_TABLE} ({column_sql})
            values ({value_sql})
            """
        ),
        insert_payload,
    )


def _safe_mark_running(run_repo: RunRepository, session: Any, run: Any) -> None:
    fn = getattr(run_repo, "mark_run_running", None)
    if fn is not None:
        fn(session, run)


def _safe_mark_success(run_repo: RunRepository, session: Any, run: Any) -> None:
    for name in ("mark_run_success", "mark_run_succeeded", "mark_success"):
        fn = getattr(run_repo, name, None)
        if fn is not None:
            fn(session, run)
            return


def _safe_mark_failed(run_repo: RunRepository, session: Any, run: Any, error: Exception) -> None:
    for name in ("mark_run_failed", "mark_failed", "mark_run_error"):
        fn = getattr(run_repo, name, None)
        if fn is not None:
            try:
                fn(session, run, error_message=str(error))
            except TypeError:
                try:
                    fn(session, run, str(error))
                except TypeError:
                    fn(session, run)
            return


def main() -> None:
    source_order_run_id = _env_int("M7_TEST_SOURCE_ORDER_RUN_ID", 112)
    portfolio_id = _env_int("M7_PORTFOLIO_ID", 1)

    remove_count = _env_int("M7_TEST_REMOVE_COUNT", 3)
    reduce_count = _env_int("M7_TEST_REDUCE_COUNT", 3)
    increase_count = _env_int("M7_TEST_INCREASE_COUNT", 3)

    reduce_ratio = _env_decimal("M7_TEST_REDUCE_RATIO", "0.5")
    increase_lots = _env_decimal("M7_TEST_INCREASE_LOTS", "1")
    lot_size = _env_decimal("M7_TEST_LOT_SIZE", "100")

    session = SessionLocal()
    run_repo = RunRepository()
    root_run = None

    try:
        columns = _get_columns(session, ORDER_TABLE)
        security_key = _resolve_security_key(columns)
        order_quantity_col = _resolve_order_quantity_col(columns)

        source_rows = session.execute(
            text(
                f"""
                select *
                from {ORDER_TABLE}
                where run_id = :source_order_run_id
                  and portfolio_id = :portfolio_id
                  and coalesce({order_quantity_col}, 0) > 0
                order by {security_key}
                """
            ),
            {
                "source_order_run_id": source_order_run_id,
                "portfolio_id": portfolio_id,
            },
        ).mappings().all()

        if not source_rows:
            raise RuntimeError(
                f"source_order_run_id={source_order_run_id}, portfolio_id={portfolio_id} 没有可复制订单"
            )

        root_run = run_repo.create_run(
            session=session,
            run_type="PAPER_TRADING",
            run_name="bootstrap_m7_rebalance_test_template_order",
            trigger_type="MANUAL",
            context_json={
                "module": "M7",
                "stage": "M7.2-C",
                "purpose": "build_test_target_quantity_template_order",
                "source_order_run_id": source_order_run_id,
                "portfolio_id": portfolio_id,
                "remove_count": remove_count,
                "reduce_count": reduce_count,
                "increase_count": increase_count,
                "reduce_ratio": str(reduce_ratio),
                "increase_lots": str(increase_lots),
                "lot_size": str(lot_size),
            },
        )
        session.commit()

        _safe_mark_running(run_repo, session, root_run)
        session.commit()

        inserted_count = 0
        removed_count = 0
        reduced_count = 0
        increased_count = 0
        unchanged_count = 0

        total_source_quantity = Decimal("0")
        total_template_quantity = Decimal("0")

        now = datetime.utcnow()

        for idx, row in enumerate(source_rows):
            row_dict = dict(row)
            source_quantity = _to_decimal(row_dict.get(order_quantity_col))
            total_source_quantity += source_quantity

            # 第一段：剔除。通过不复制模板行实现 target_quantity = 0。
            if idx < remove_count:
                removed_count += 1
                continue

            # 第二段：减仓。
            if idx < remove_count + reduce_count:
                target_quantity = _floor_to_lot(source_quantity * reduce_ratio, lot_size)
                if target_quantity >= source_quantity and source_quantity >= lot_size:
                    target_quantity = source_quantity - lot_size
                target_quantity = max(target_quantity, Decimal("0"))
                reduced_count += 1

            # 第三段：增仓。
            elif idx < remove_count + reduce_count + increase_count:
                target_quantity = source_quantity + increase_lots * lot_size
                increased_count += 1

            # 其余：不变。
            else:
                target_quantity = source_quantity
                unchanged_count += 1

            row_dict["run_id"] = root_run.id
            row_dict[order_quantity_col] = target_quantity

            for col in ("filled_quantity", "fill_quantity"):
                if col in row_dict:
                    row_dict[col] = Decimal("0")

            for col in ("remaining_quantity", "unfilled_quantity"):
                if col in row_dict:
                    row_dict[col] = target_quantity

            for col in ("order_status", "status"):
                if col in row_dict:
                    row_dict[col] = "CREATED"

            for col in ("created_at", "updated_at", "created_time", "updated_time"):
                if col in row_dict:
                    row_dict[col] = now

            _copy_insert_order(session, columns=columns, payload=row_dict)

            inserted_count += 1
            total_template_quantity += target_quantity

        _safe_mark_success(run_repo, session, root_run)
        session.commit()

        output = {
            "m7_test_template_order_run_id": root_run.id,
            "source_order_run_id": source_order_run_id,
            "portfolio_id": portfolio_id,
            "source_count": len(source_rows),
            "inserted_template_count": inserted_count,
            "removed_count": removed_count,
            "reduced_count": reduced_count,
            "increased_count": increased_count,
            "unchanged_count": unchanged_count,
            "total_source_quantity": str(total_source_quantity),
            "total_template_quantity": str(total_template_quantity),
            "security_key": security_key,
            "order_quantity_col": order_quantity_col,
            "status": "SUCCESS",
        }

        print(json.dumps(output, ensure_ascii=False, indent=2, default=str))

    except Exception as exc:
        session.rollback()
        if root_run is not None:
            try:
                _safe_mark_failed(run_repo, session, root_run, exc)
                session.commit()
            except Exception:
                session.rollback()
        raise

    finally:
        session.close()


if __name__ == "__main__":
    main()
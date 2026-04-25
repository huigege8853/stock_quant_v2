from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


POSITION_TABLE = "trading_paper_position"


@dataclass(frozen=True)
class PositionCarryResult:
    source_position_run_id: int
    target_position_run_id: int
    portfolio_id: int
    source_effective_date: str | None
    target_effective_date: str
    source_count: int
    deleted_existing_count: int
    inserted_count: int
    source_quantity_total: str
    target_quantity_total: str
    target_available_quantity_total: str
    status: str


class PaperPositionCarryService:
    """
    M7.1: Paper position carry-forward service.

    目标：
    1. 将上一交易日 position run 的持仓滚动到下一交易日 position run。
    2. 执行 A 股 T+1 语义：上一交易日买入的持仓，到下一交易日 available_quantity = quantity。
    3. 不做 BUY / SELL / realized_pnl / valuation。
    4. 尽量复用 M6 trading_paper_position 表，不强依赖 ORM 字段。
    """

    def __init__(self, session: Session):
        self.session = session

    def carry_forward(
        self,
        *,
        source_position_run_id: int,
        target_position_run_id: int,
        portfolio_id: int,
        target_effective_date: date,
        source_effective_date: date | None = None,
        target_as_of_date: date | None = None,
        replace_existing: bool = False,
    ) -> PositionCarryResult:
        columns = self._get_table_columns(POSITION_TABLE)

        required_columns = {"run_id", "portfolio_id", "quantity"}
        missing_columns = sorted(required_columns - set(columns))
        if missing_columns:
            raise RuntimeError(
                f"{POSITION_TABLE} 缺少 M7.1 carry forward 必需字段: {missing_columns}"
            )

        if "available_quantity" not in columns:
            raise RuntimeError(
                f"{POSITION_TABLE} 缺少 available_quantity，无法执行 T+1 可卖数量更新。"
            )

        existing_count = self._count_positions(
            run_id=target_position_run_id,
            portfolio_id=portfolio_id,
        )

        deleted_existing_count = 0
        if existing_count > 0:
            if not replace_existing:
                raise RuntimeError(
                    f"目标 run 已存在持仓: target_position_run_id={target_position_run_id}, "
                    f"portfolio_id={portfolio_id}, count={existing_count}. "
                    f"如确认重跑，请设置 replace_existing=True 或环境变量 M7_REPLACE_EXISTING=true。"
                )
            deleted_existing_count = self._delete_positions(
                run_id=target_position_run_id,
                portfolio_id=portfolio_id,
            )

        source_rows = self._load_source_positions(
            columns=columns,
            source_position_run_id=source_position_run_id,
            portfolio_id=portfolio_id,
            source_effective_date=source_effective_date,
        )

        inserted_count = 0
        for source_row in source_rows:
            payload = self._build_target_payload(
                source_row=source_row,
                columns=columns,
                source_position_run_id=source_position_run_id,
                target_position_run_id=target_position_run_id,
                target_effective_date=target_effective_date,
                target_as_of_date=target_as_of_date or target_effective_date,
            )
            self._insert_position(payload)
            inserted_count += 1

        source_quantity_total = self._sum_quantity(
            run_id=source_position_run_id,
            portfolio_id=portfolio_id,
        )
        target_quantity_total = self._sum_quantity(
            run_id=target_position_run_id,
            portfolio_id=portfolio_id,
        )
        target_available_quantity_total = self._sum_available_quantity(
            run_id=target_position_run_id,
            portfolio_id=portfolio_id,
        )

        return PositionCarryResult(
            source_position_run_id=source_position_run_id,
            target_position_run_id=target_position_run_id,
            portfolio_id=portfolio_id,
            source_effective_date=source_effective_date.isoformat()
            if source_effective_date
            else None,
            target_effective_date=target_effective_date.isoformat(),
            source_count=len(source_rows),
            deleted_existing_count=deleted_existing_count,
            inserted_count=inserted_count,
            source_quantity_total=str(source_quantity_total),
            target_quantity_total=str(target_quantity_total),
            target_available_quantity_total=str(target_available_quantity_total),
            status="SUCCESS",
        )

    def _get_table_columns(self, table_name: str) -> list[str]:
        rows = self.session.execute(
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

    def _count_positions(self, *, run_id: int, portfolio_id: int) -> int:
        row = self.session.execute(
            text(
                f"""
                select count(*) as cnt
                from {POSITION_TABLE}
                where run_id = :run_id
                  and portfolio_id = :portfolio_id
                """
            ),
            {"run_id": run_id, "portfolio_id": portfolio_id},
        ).mappings().one()
        return int(row["cnt"] or 0)

    def _delete_positions(self, *, run_id: int, portfolio_id: int) -> int:
        result = self.session.execute(
            text(
                f"""
                delete from {POSITION_TABLE}
                where run_id = :run_id
                  and portfolio_id = :portfolio_id
                """
            ),
            {"run_id": run_id, "portfolio_id": portfolio_id},
        )
        return int(result.rowcount or 0)

    def _load_source_positions(
        self,
        *,
        columns: list[str],
        source_position_run_id: int,
        portfolio_id: int,
        source_effective_date: date | None,
    ) -> list[dict[str, Any]]:
        date_filter_sql = ""
        params: dict[str, Any] = {
            "source_position_run_id": source_position_run_id,
            "portfolio_id": portfolio_id,
        }

        if source_effective_date is not None:
            for date_col in ("effective_date", "snapshot_date", "trade_date", "position_date"):
                if date_col in columns:
                    date_filter_sql = f" and {date_col} = :source_effective_date"
                    params["source_effective_date"] = source_effective_date
                    break

        rows = self.session.execute(
            text(
                f"""
                select *
                from {POSITION_TABLE}
                where run_id = :source_position_run_id
                  and portfolio_id = :portfolio_id
                  and coalesce(quantity, 0) > 0
                  {date_filter_sql}
                order by id
                """
            ),
            params,
        ).mappings().all()

        return [dict(row) for row in rows]

    def _build_target_payload(
        self,
        *,
        source_row: dict[str, Any],
        columns: list[str],
        source_position_run_id: int,
        target_position_run_id: int,
        target_effective_date: date,
        target_as_of_date: date,
    ) -> dict[str, Any]:
        now = datetime.utcnow()
        quantity = self._to_decimal(source_row.get("quantity"))

        payload: dict[str, Any] = {}

        skip_columns = {
            "id",
            "created_id",
            "updated_id",
        }

        for column in columns:
            if column in skip_columns:
                continue

            if column == "run_id":
                payload[column] = target_position_run_id
            elif column == "portfolio_id":
                payload[column] = source_row.get(column)
            elif column in {"effective_date", "snapshot_date", "trade_date", "position_date"}:
                payload[column] = target_effective_date
            elif column == "as_of_date":
                payload[column] = target_as_of_date
            elif column == "available_quantity":
                payload[column] = quantity
            elif column == "frozen_quantity":
                payload[column] = Decimal("0")
            elif column in {"carry_source_run_id", "source_position_run_id"}:
                payload[column] = source_position_run_id
            elif column in {"carry_source_position_id", "source_position_id"}:
                payload[column] = source_row.get("id")
            elif column in {"position_status", "status"}:
                payload[column] = "OPEN" if quantity > 0 else "CLOSED"
            elif column in {"created_at", "updated_at"}:
                payload[column] = now
            elif column in {"created_time", "updated_time"}:
                payload[column] = now
            else:
                payload[column] = source_row.get(column)

        return payload

    def _insert_position(self, payload: dict[str, Any]) -> None:
        if not payload:
            raise RuntimeError("insert payload is empty")

        columns = list(payload.keys())
        column_sql = ", ".join([f'"{col}"' for col in columns])
        value_sql = ", ".join([f":{col}" for col in columns])

        self.session.execute(
            text(
                f"""
                insert into {POSITION_TABLE} ({column_sql})
                values ({value_sql})
                """
            ),
            payload,
        )

    def _sum_quantity(self, *, run_id: int, portfolio_id: int) -> Decimal:
        row = self.session.execute(
            text(
                f"""
                select coalesce(sum(quantity), 0) as total_quantity
                from {POSITION_TABLE}
                where run_id = :run_id
                  and portfolio_id = :portfolio_id
                """
            ),
            {"run_id": run_id, "portfolio_id": portfolio_id},
        ).mappings().one()
        return self._to_decimal(row["total_quantity"])

    def _sum_available_quantity(self, *, run_id: int, portfolio_id: int) -> Decimal:
        row = self.session.execute(
            text(
                f"""
                select coalesce(sum(available_quantity), 0) as total_available_quantity
                from {POSITION_TABLE}
                where run_id = :run_id
                  and portfolio_id = :portfolio_id
                """
            ),
            {"run_id": run_id, "portfolio_id": portfolio_id},
        ).mappings().one()
        return self._to_decimal(row["total_available_quantity"])

    @staticmethod
    def _to_decimal(value: Any) -> Decimal:
        if value is None:
            return Decimal("0")
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))


def result_to_dict(result: PositionCarryResult) -> dict[str, Any]:
    return asdict(result)
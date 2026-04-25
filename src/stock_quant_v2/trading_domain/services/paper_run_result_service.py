import json
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


class PaperRunResultService:
    def __init__(self, session: Session):
        self.session = session

    def write_results_for_chain(
        self,
        result_run_id: int,
        portfolio_id: int,
        target_run_id: int,
        order_run_id: int,
        fill_run_id: int,
        position_snapshot_run_id: int,
        ledger_run_id: int | None,
    ) -> dict:
        snapshot = self._load_snapshot(
            run_id=position_snapshot_run_id,
            portfolio_id=portfolio_id,
        )

        snapshot_date = snapshot["snapshot_date"]

        counts = self._load_counts(
            portfolio_id=portfolio_id,
            target_run_id=target_run_id,
            order_run_id=order_run_id,
            fill_run_id=fill_run_id,
            position_snapshot_run_id=position_snapshot_run_id,
            ledger_run_id=ledger_run_id,
        )

        fill_agg = self._load_fill_agg(
            portfolio_id=portfolio_id,
            fill_run_id=fill_run_id,
        )

        self._delete_existing_metric_rows(result_run_id=result_run_id)
        self._delete_existing_series_rows(result_run_id=result_run_id)

        metrics = self._build_metrics(
            snapshot=snapshot,
            counts=counts,
            fill_agg=fill_agg,
            snapshot_date=snapshot_date,
            chain={
                "target_run_id": target_run_id,
                "order_run_id": order_run_id,
                "fill_run_id": fill_run_id,
                "position_snapshot_run_id": position_snapshot_run_id,
                "ledger_run_id": ledger_run_id,
            },
        )

        series = self._build_series(snapshot=snapshot)

        metric_written = 0
        for metric in metrics:
            self._insert_dynamic(
                table_name="ops_run_metric_snapshot",
                values=self._metric_values(
                    result_run_id=result_run_id,
                    metric=metric,
                    snapshot_date=snapshot_date,
                ),
            )
            metric_written += 1

        series_written = 0
        for item in series:
            self._insert_dynamic(
                table_name="ops_run_series_snapshot",
                values=self._series_values(
                    result_run_id=result_run_id,
                    item=item,
                    snapshot_date=snapshot_date,
                ),
            )
            series_written += 1

        self.session.flush()

        return {
            "result_run_id": result_run_id,
            "portfolio_id": portfolio_id,
            "snapshot_date": snapshot_date.isoformat(),
            "metric_written": metric_written,
            "series_written": series_written,
        }

    def _load_snapshot(self, run_id: int, portfolio_id: int) -> dict:
        row = self.session.execute(
            text(
                """
                select *
                from trading_paper_portfolio_snapshot
                where run_id = :run_id
                  and portfolio_id = :portfolio_id
                limit 1
                """
            ),
            {
                "run_id": run_id,
                "portfolio_id": portfolio_id,
            },
        ).mappings().one_or_none()

        if row is None:
            raise ValueError(
                f"snapshot not found: run_id={run_id}, portfolio_id={portfolio_id}"
            )

        return dict(row)

    def _load_counts(
        self,
        portfolio_id: int,
        target_run_id: int,
        order_run_id: int,
        fill_run_id: int,
        position_snapshot_run_id: int,
        ledger_run_id: int | None,
    ) -> dict[str, int]:
        result = {
            "target_count": self._count(
                "trading_paper_target_position",
                target_run_id,
                portfolio_id,
            ),
            "order_count": self._count(
                "trading_paper_order",
                order_run_id,
                portfolio_id,
            ),
            "fill_count": self._count(
                "trading_paper_fill",
                fill_run_id,
                portfolio_id,
            ),
            "position_count": self._count(
                "trading_paper_position",
                position_snapshot_run_id,
                portfolio_id,
            ),
            "snapshot_count": self._count(
                "trading_paper_portfolio_snapshot",
                position_snapshot_run_id,
                portfolio_id,
            ),
            "ledger_count": 0,
        }

        if ledger_run_id is not None:
            result["ledger_count"] = self._count(
                "trading_paper_trade_ledger",
                ledger_run_id,
                portfolio_id,
            )

        return result

    def _count(self, table_name: str, run_id: int, portfolio_id: int) -> int:
        value = self.session.execute(
            text(
                f"""
                select count(*)
                from {table_name}
                where run_id = :run_id
                  and portfolio_id = :portfolio_id
                """
            ),
            {
                "run_id": run_id,
                "portfolio_id": portfolio_id,
            },
        ).scalar_one()

        return int(value or 0)

    def _load_fill_agg(self, portfolio_id: int, fill_run_id: int) -> dict:
        row = self.session.execute(
            text(
                """
                select
                    coalesce(sum(gross_amount), 0) as total_gross_amount,
                    coalesce(sum(total_fee_amount), 0) as total_fee_amount,
                    coalesce(sum(net_amount), 0) as total_net_amount,
                    coalesce(sum(cash_delta), 0) as total_cash_delta,
                    coalesce(sum(slippage_amount), 0) as total_slippage_amount
                from trading_paper_fill
                where run_id = :fill_run_id
                  and portfolio_id = :portfolio_id
                  and fill_status = 'COMPLETED'
                """
            ),
            {
                "fill_run_id": fill_run_id,
                "portfolio_id": portfolio_id,
            },
        ).mappings().one()

        return dict(row)

    def _build_metrics(
        self,
        snapshot: dict,
        counts: dict,
        fill_agg: dict,
        snapshot_date: date,
        chain: dict,
    ) -> list[dict]:
        return [
            self._metric("m6.paper.target_count", counts["target_count"]),
            self._metric("m6.paper.order_count", counts["order_count"]),
            self._metric("m6.paper.fill_count", counts["fill_count"]),
            self._metric("m6.paper.position_count", counts["position_count"]),
            self._metric("m6.paper.snapshot_count", counts["snapshot_count"]),
            self._metric("m6.paper.ledger_count", counts["ledger_count"]),
            self._metric("m6.paper.holding_count", snapshot["holding_count"]),
            self._metric("m6.paper.cash_balance", snapshot["cash_balance"]),
            self._metric("m6.paper.market_value", snapshot["market_value"]),
            self._metric("m6.paper.total_equity", snapshot["total_equity"]),
            self._metric("m6.paper.daily_pnl", snapshot["daily_pnl"]),
            self._metric("m6.paper.cumulative_pnl", snapshot["cumulative_pnl"]),
            self._metric("m6.paper.daily_return", snapshot["daily_return"]),
            self._metric("m6.paper.cumulative_return", snapshot["cumulative_return"]),
            self._metric("m6.paper.turnover_amount", snapshot["turnover_amount"]),
            self._metric("m6.paper.turnover_rate", snapshot["turnover_rate"]),
            self._metric("m6.paper.total_gross_amount", fill_agg["total_gross_amount"]),
            self._metric("m6.paper.total_fee_amount", fill_agg["total_fee_amount"]),
            self._metric("m6.paper.total_net_amount", fill_agg["total_net_amount"]),
            self._metric("m6.paper.total_cash_delta", fill_agg["total_cash_delta"]),
            self._metric(
                "m6.paper.total_slippage_amount",
                fill_agg["total_slippage_amount"],
            ),
            self._metric(
                "m6.paper.quality_pass",
                Decimal("1"),
                payload={
                    "snapshot_date": snapshot_date.isoformat(),
                    "chain": chain,
                },
            ),
        ]

    def _metric(
        self,
        code: str,
        value: Any,
        payload: dict | None = None,
    ) -> dict:
        return {
            "code": code,
            "name": code,
            "value": self._decimal(value),
            "payload": payload or {},
        }

    def _build_series(self, snapshot: dict) -> list[dict]:
        return [
            self._series("m6.paper.cash_balance", snapshot["cash_balance"]),
            self._series("m6.paper.market_value", snapshot["market_value"]),
            self._series("m6.paper.total_equity", snapshot["total_equity"]),
            self._series("m6.paper.holding_count", snapshot["holding_count"]),
            self._series("m6.paper.gross_exposure", snapshot["gross_exposure"]),
            self._series("m6.paper.net_exposure", snapshot["net_exposure"]),
            self._series("m6.paper.daily_pnl", snapshot["daily_pnl"]),
            self._series("m6.paper.cumulative_return", snapshot["cumulative_return"]),
            self._series("m6.paper.turnover_rate", snapshot["turnover_rate"]),
        ]

    def _series(self, code: str, value: Any) -> dict:
        return {
            "code": code,
            "name": code,
            "value": self._decimal(value),
        }

    def _metric_values(
            self,
            result_run_id: int,
            metric: dict,
            snapshot_date: date,
    ) -> dict:
        payload_json = json.dumps(
            {
                "module": "M6",
                "domain": "paper_trading",
                "metric_code": metric["code"],
                **metric["payload"],
            },
            ensure_ascii=False,
        )

        value = metric["value"]

        return {
            "run_id": result_run_id,

            # M5 / ops_run_metric_snapshot common identity columns
            "metric_namespace": "M6_PAPER_TRADING",
            "metric_code": metric["code"],
            "metric_name": metric["name"],
            "metric_category": "M6_PAPER_TRADING",
            "metric_group": "M6_PAPER_TRADING",

            # Common numeric/text/json value columns
            "metric_value_numeric": value,
            "metric_value": value,
            "value_numeric": value,
            "numeric_value": value,
            "metric_value_text": str(value),
            "value_text": str(value),
            "metric_value_json": payload_json,
            "payload_json": payload_json,
            "value_json": payload_json,

            # Common metadata columns
            "unit": None,
            "metric_unit": None,
            "as_of_date": snapshot_date,
            "trade_date": snapshot_date,
            "snapshot_date": snapshot_date,

            # Common scope/order columns observed in current DB
            "subject_type": "PORTFOLIO",
            "subject_key": "ALL",
            "scope_type": "PORTFOLIO",
            "scope_key": "ALL",
            "dimension_type": "PORTFOLIO",
            "dimension_key": "ALL",
            "sort_order": 0,
        }

    def _series_values(
            self,
            result_run_id: int,
            item: dict,
            snapshot_date: date,
    ) -> dict:
        payload_json = json.dumps(
            {
                "module": "M6",
                "domain": "paper_trading",
                "series_code": item["code"],
            },
            ensure_ascii=False,
        )

        value = item["value"]

        return {
            "run_id": result_run_id,

            # M5 / ops_run_series_snapshot common identity columns
            "series_namespace": "M6_PAPER_TRADING",
            "series_code": item["code"],
            "series_name": item["name"],
            "series_category": "M6_PAPER_TRADING",
            "series_group": "M6_PAPER_TRADING",
            "series_type": "DAILY",

            # Common x/date columns
            "series_date": snapshot_date,
            "trade_date": snapshot_date,
            "as_of_date": snapshot_date,
            "snapshot_date": snapshot_date,
            "x_date": snapshot_date,
            "x_value": snapshot_date.isoformat(),

            # Common y/value columns
            "series_value_numeric": value,
            "y_value_numeric": value,
            "value_numeric": value,
            "numeric_value": value,
            "series_value_text": str(value),
            "value_text": str(value),
            "series_value_json": payload_json,
            "payload_json": payload_json,
            "value_json": payload_json,

            # Common scope/order columns
            "subject_type": "PORTFOLIO",
            "subject_key": "ALL",
            "scope_type": "PORTFOLIO",
            "scope_key": "ALL",
            "dimension_type": "PORTFOLIO",
            "dimension_key": "ALL",
            "sort_order": 0,
        }

    def _delete_existing_metric_rows(self, result_run_id: int) -> None:
        columns = self._get_table_columns("ops_run_metric_snapshot")
        if "metric_code" in columns:
            self.session.execute(
                text(
                    """
                    delete from ops_run_metric_snapshot
                    where run_id = :run_id
                      and metric_code like 'm6.paper.%'
                    """
                ),
                {"run_id": result_run_id},
            )
        else:
            self.session.execute(
                text("delete from ops_run_metric_snapshot where run_id = :run_id"),
                {"run_id": result_run_id},
            )

    def _delete_existing_series_rows(self, result_run_id: int) -> None:
        columns = self._get_table_columns("ops_run_series_snapshot")
        if "series_code" in columns:
            self.session.execute(
                text(
                    """
                    delete from ops_run_series_snapshot
                    where run_id = :run_id
                      and series_code like 'm6.paper.%'
                    """
                ),
                {"run_id": result_run_id},
            )
        else:
            self.session.execute(
                text("delete from ops_run_series_snapshot where run_id = :run_id"),
                {"run_id": result_run_id},
            )

    def _insert_dynamic(self, table_name: str, values: dict) -> None:
        column_types = self._get_table_column_types(table_name)
        nullable_map = self._get_table_nullable_map(table_name)
        defaults_map = self._get_table_defaults_map(table_name)

        available_columns = set(column_types.keys())

        enriched_values = dict(values)

        # Generic not-null compatibility defaults.
        compatibility_defaults = {
            "metric_namespace": "M6_PAPER_TRADING",
            "series_namespace": "M6_PAPER_TRADING",
            "subject_type": "PORTFOLIO",
            "subject_key": "ALL",
            "scope_type": "PORTFOLIO",
            "scope_key": "ALL",
            "dimension_type": "PORTFOLIO",
            "dimension_key": "ALL",
            "sort_order": 0,
            "is_primary": False,
            "is_active": True,
        }

        for col, default_value in compatibility_defaults.items():
            if col in available_columns and col not in enriched_values:
                enriched_values[col] = default_value

        # Only insert compatible columns.
        insert_values = {
            key: value
            for key, value in enriched_values.items()
            if key in available_columns
        }

        # Guard: fill remaining NOT NULL columns that have no DB default.
        missing_required = []
        for col in available_columns:
            if col in insert_values:
                continue

            if col == "id":
                continue

            is_nullable = nullable_map.get(col, "YES")
            has_default = defaults_map.get(col) is not None

            if is_nullable == "NO" and not has_default:
                missing_required.append(col)

        if missing_required:
            raise ValueError(
                f"Missing required columns for {table_name}: {missing_required}. "
                f"Available inserted columns={sorted(insert_values.keys())}"
            )

        if not insert_values:
            raise ValueError(f"No compatible columns found for table={table_name}")

        columns = list(insert_values.keys())
        placeholders = []

        for col in columns:
            data_type = column_types[col]
            if data_type in {"json", "jsonb"}:
                placeholders.append(f"cast(:{col} as jsonb)")
            else:
                placeholders.append(f":{col}")

        sql = text(
            f"""
            insert into {table_name} (
                {", ".join(columns)}
            )
            values (
                {", ".join(placeholders)}
            )
            """
        )

        self.session.execute(sql, insert_values)

    def _get_table_columns(self, table_name: str) -> set[str]:
        return set(self._get_table_column_types(table_name).keys())

    def _get_table_column_types(self, table_name: str) -> dict[str, str]:
        rows = self.session.execute(
            text(
                """
                select
                    column_name,
                    data_type
                from information_schema.columns
                where table_schema = 'public'
                  and table_name = :table_name
                """
            ),
            {"table_name": table_name},
        ).all()

        if not rows:
            raise ValueError(f"table not found or has no columns: {table_name}")

        return {row[0]: row[1] for row in rows}

    def _get_table_nullable_map(self, table_name: str) -> dict[str, str]:
        rows = self.session.execute(
            text(
                """
                select
                    column_name,
                    is_nullable
                from information_schema.columns
                where table_schema = 'public'
                  and table_name = :table_name
                """
            ),
            {"table_name": table_name},
        ).all()

        if not rows:
            raise ValueError(f"table not found or has no columns: {table_name}")

        return {row[0]: row[1] for row in rows}

    def _get_table_defaults_map(self, table_name: str) -> dict[str, str | None]:
        rows = self.session.execute(
            text(
                """
                select
                    column_name,
                    column_default
                from information_schema.columns
                where table_schema = 'public'
                  and table_name = :table_name
                """
            ),
            {"table_name": table_name},
        ).all()

        if not rows:
            raise ValueError(f"table not found or has no columns: {table_name}")

        return {row[0]: row[1] for row in rows}

    @staticmethod
    def _decimal(value: Any) -> Decimal:
        if value is None:
            return Decimal("0")
        return Decimal(str(value))
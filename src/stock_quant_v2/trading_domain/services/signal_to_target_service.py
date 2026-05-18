from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from stock_quant_v2.trading_domain.dto.target_position import (
    BuildTargetPositionRequestDTO,
    PaperTargetPositionCreateDTO,
)
from stock_quant_v2.trading_domain.repositories.target_position_repository import (
    TargetPositionRepository,
)


class SignalToTargetService:
    """
    Convert strategy_signal rows into trading_paper_target_position rows.

    M7.7 enhancement:
    - keep strategy_signal unchanged;
    - calculate target_amount and target_quantity in target_position;
    - use as_of close / latest available close for sizing to avoid future leakage;
    - round A-share quantities down to board lot size, default 100 shares.
    """

    def __init__(self, session: Session):
        self.session = session
        self.target_repo = TargetPositionRepository(session)

    def build_equal_weight_targets(
        self,
        request: BuildTargetPositionRequestDTO,
    ):
        if request.target_count <= 0:
            raise ValueError("target_count must be positive")

        if request.construction_mode != "EQUAL_WEIGHT_SELECTED":
            raise ValueError(
                f"unsupported construction_mode: {request.construction_mode}"
            )

        if request.long_only is False:
            raise ValueError("M7.7 only supports long_only=True")

        if request.sizing_mode not in {"EQUAL_WEIGHT_BY_EQUITY", "EQUAL_WEIGHT_BY_CASH"}:
            raise ValueError(
                "unsupported sizing_mode: "
                f"{request.sizing_mode}. Expected EQUAL_WEIGHT_BY_EQUITY/EQUAL_WEIGHT_BY_CASH"
            )

        lot_size = self._to_decimal(request.lot_size)
        if lot_size <= 0:
            raise ValueError("lot_size must be positive")

        cash_buffer_rate = self._to_decimal(request.cash_buffer_rate)
        if cash_buffer_rate < 0 or cash_buffer_rate >= 1:
            raise ValueError("cash_buffer_rate must be >= 0 and < 1")

        rows = self._load_selected_strategy_signals(
            source_signal_run_id=request.source_signal_run_id,
            as_of_date=request.as_of_date,
            effective_date=request.effective_date,
            limit=request.target_count,
        )

        if not rows:
            diagnostics = self._diagnose_strategy_signal(
                source_signal_run_id=request.source_signal_run_id
            )
            raise ValueError(
                "no strategy_signal rows found for target generation. "
                f"run_id={request.source_signal_run_id}, "
                f"as_of_date={request.as_of_date}, "
                f"effective_date={request.effective_date}, "
                f"diagnostics={diagnostics}"
            )

        sizing_capital = self._resolve_sizing_capital(request)
        deployable_capital = self._money(sizing_capital * (Decimal("1") - cash_buffer_rate))

        target_weight = (
            Decimal("1") / Decimal(str(len(rows)))
        ).quantize(Decimal("0.0000000001"), rounding=ROUND_HALF_UP)

        price_date = request.price_date or request.as_of_date
        items: list[PaperTargetPositionCreateDTO] = []

        for idx, row in enumerate(rows, start=1):
            instrument_id = int(row["instrument_id"])
            price_info = self._resolve_sizing_price(
                instrument_id=instrument_id,
                price_date=price_date,
                price_source=request.price_source,
            )
            sizing_price = price_info["price"]

            raw_target_amount = self._money(deployable_capital * target_weight)
            target_quantity = self._floor_to_lot(raw_target_amount / sizing_price, lot_size)
            target_amount = self._money(target_quantity * sizing_price)

            status = "PENDING"
            status_reason = (
                f"M7_7_SIZED_BY_{request.sizing_mode};"
                f"price_source={price_info['source']};"
                f"price_date={price_info['date']};"
                f"price={sizing_price};"
                f"lot_size={lot_size};"
                f"raw_target_amount={raw_target_amount};"
                f"cash_buffer_rate={cash_buffer_rate}"
            )
            if target_quantity <= 0:
                status = "REJECTED"
                status_reason = "M7_7_ZERO_TARGET_QUANTITY;" + status_reason

            items.append(
                PaperTargetPositionCreateDTO(
                    run_id=request.run_id,
                    portfolio_id=request.portfolio_id,
                    source_signal_run_id=request.source_signal_run_id,
                    source_screen_request_id=request.source_screen_request_id,
                    strategy_signal_id=row["strategy_signal_id"],
                    as_of_date=request.as_of_date,
                    effective_date=request.effective_date,
                    instrument_id=instrument_id,
                    target_side="LONG",
                    target_weight=target_weight,
                    target_amount=target_amount,
                    target_quantity=target_quantity,
                    rank_no=idx,
                    score=row.get("score"),
                    reason_code=row.get("reason_code") or "TOP_N_SELECTED",
                    target_source="STRATEGY_SIGNAL_SIZED",
                    construction_mode=request.construction_mode,
                    status=status,
                    status_reason=status_reason[:255],
                )
            )

        self.target_repo.delete_by_run_portfolio_date(
            run_id=request.run_id,
            portfolio_id=request.portfolio_id,
            effective_date=request.effective_date,
        )

        return self.target_repo.bulk_create(items)

    def _resolve_sizing_capital(self, request: BuildTargetPositionRequestDTO) -> Decimal:
        explicit_capital = self._to_decimal(request.sizing_capital)
        if explicit_capital > 0:
            return explicit_capital

        snapshot_columns = self._get_table_columns("trading_paper_portfolio_snapshot")
        if snapshot_columns:
            capital_col = None
            if request.sizing_mode == "EQUAL_WEIGHT_BY_CASH":
                capital_col = self._pick_first_existing_column(
                    snapshot_columns,
                    ["cash_balance", "cash", "available_cash", "cash_amount"],
                )
            else:
                capital_col = self._pick_first_existing_column(
                    snapshot_columns,
                    ["total_equity", "net_liquidation", "portfolio_value", "cash_balance"],
                )

            date_col = self._pick_first_existing_column(
                snapshot_columns,
                ["snapshot_date", "as_of_date", "effective_date", "trade_date"],
            )

            if capital_col and date_col:
                row = self.session.execute(
                    text(
                        f"""
                        select {capital_col} as capital
                        from trading_paper_portfolio_snapshot
                        where portfolio_id = :portfolio_id
                          and {date_col} <= :as_of_date
                          and coalesce({capital_col}, 0) > 0
                        order by {date_col} desc, id desc
                        limit 1
                        """
                    ),
                    {
                        "portfolio_id": request.portfolio_id,
                        "as_of_date": request.as_of_date,
                    },
                ).mappings().first()
                if row is not None:
                    capital = self._to_decimal(row["capital"])
                    if capital > 0:
                        return capital

        row = self.session.execute(
            text(
                """
                select initial_cash
                from trading_paper_portfolio
                where id = :portfolio_id
                limit 1
                """
            ),
            {"portfolio_id": request.portfolio_id},
        ).mappings().first()
        if row is not None:
            capital = self._to_decimal(row["initial_cash"])
            if capital > 0:
                return capital

        raise RuntimeError(
            "Cannot resolve sizing capital. Set M7_TARGET_SIZING_CAPITAL or make sure "
            "trading_paper_portfolio_snapshot / trading_paper_portfolio has positive capital."
        )

    def _resolve_sizing_price(
        self,
        *,
        instrument_id: int,
        price_date: date,
        price_source: str,
    ) -> dict[str, Any]:
        columns = self._get_table_columns("core_daily_bar")
        if "instrument_id" not in columns:
            raise RuntimeError("core_daily_bar is missing instrument_id")

        date_col = self._pick_first_existing_column(columns, ["trade_date", "bar_date", "date"])
        if date_col is None:
            raise RuntimeError("core_daily_bar cannot resolve date column")

        price_source = (price_source or "AS_OF_CLOSE").upper()
        if price_source in {"AS_OF_OPEN", "OPEN"}:
            price_candidates = ["open_price", "open", "adj_open", "open_adj"]
        else:
            price_candidates = ["close_price", "close", "adj_close", "close_adj"]

        price_col = self._pick_first_existing_column(columns, price_candidates)
        if price_col is None:
            raise RuntimeError(
                f"core_daily_bar cannot resolve price column for price_source={price_source}"
            )

        # Exact as-of date first.
        row = self.session.execute(
            text(
                f"""
                select {price_col} as price, {date_col} as price_date
                from core_daily_bar
                where instrument_id = :instrument_id
                  and {date_col} = :price_date
                  and coalesce({price_col}, 0) > 0
                limit 1
                """
            ),
            {"instrument_id": instrument_id, "price_date": price_date},
        ).mappings().first()

        if row is None:
            # Fallback to latest known price <= price_date; still non-leaking.
            row = self.session.execute(
                text(
                    f"""
                    select {price_col} as price, {date_col} as price_date
                    from core_daily_bar
                    where instrument_id = :instrument_id
                      and {date_col} <= :price_date
                      and coalesce({price_col}, 0) > 0
                    order by {date_col} desc
                    limit 1
                    """
                ),
                {"instrument_id": instrument_id, "price_date": price_date},
            ).mappings().first()

        if row is None:
            raise RuntimeError(
                "Cannot resolve sizing price from core_daily_bar: "
                f"instrument_id={instrument_id}, price_date={price_date}, price_source={price_source}"
            )

        price = self._to_decimal(row["price"])
        if price <= 0:
            raise RuntimeError(
                f"resolved non-positive sizing price: instrument_id={instrument_id}, price={price}"
            )

        return {
            "price": price,
            "date": row["price_date"],
            "source": f"core_daily_bar.{price_col}",
        }

    def _load_selected_strategy_signals(
        self,
        source_signal_run_id: int,
        as_of_date: date,
        effective_date: date,
        limit: int,
    ) -> list[dict]:
        columns = self._get_table_columns("strategy_signal")

        rank_col = self._pick_first_existing_column(
            columns,
            ["rank_in_batch", "rank_no", "signal_rank", "selection_rank"],
        )
        score_col = self._pick_first_existing_column(
            columns,
            [
                "raw_score",
                "normalized_score",
                "score",
                "signal_score",
                "final_score",
                "selection_score",
                "alpha_score",
            ],
        )
        confidence_col = self._pick_first_existing_column(
            columns,
            ["confidence_score", "confidence", "signal_confidence"],
        )
        reason_col = self._pick_first_existing_column(
            columns,
            ["reason_code", "reason_codes", "signal_reason_code"],
        )
        as_of_col = self._pick_first_existing_column(
            columns,
            ["as_of_date", "signal_date", "trade_date"],
        )
        effective_col = self._pick_first_existing_column(
            columns,
            ["effective_date"],
        )

        # 1) Exact target-date match first.
        rows = self._query_strategy_signals(
            source_signal_run_id=source_signal_run_id,
            as_of_date=as_of_date,
            effective_date=effective_date,
            limit=limit,
            rank_col=rank_col,
            score_col=score_col,
            confidence_col=confidence_col,
            reason_col=reason_col,
            as_of_col=as_of_col,
            effective_col=effective_col,
            filter_reason=True,
            filter_dates=True,
        )
        if rows:
            return rows

        rows = self._query_strategy_signals(
            source_signal_run_id=source_signal_run_id,
            as_of_date=as_of_date,
            effective_date=effective_date,
            limit=limit,
            rank_col=rank_col,
            score_col=score_col,
            confidence_col=confidence_col,
            reason_col=reason_col,
            as_of_col=as_of_col,
            effective_col=effective_col,
            filter_reason=False,
            filter_dates=True,
        )
        if rows:
            return rows

        # 2) If the target execution date has no new signal, explicitly carry the
        # latest signal date <= target date for this run. This replaces the old
        # broad run_id-only fallback and avoids silently using future or unrelated
        # signal rows.
        resolved_dates = self._resolve_latest_signal_dates_for_run(
            source_signal_run_id=source_signal_run_id,
            effective_date=effective_date,
            as_of_col=as_of_col,
            effective_col=effective_col,
        )
        if resolved_dates is not None:
            source_as_of_date, source_effective_date = resolved_dates

            rows = self._query_strategy_signals(
                source_signal_run_id=source_signal_run_id,
                as_of_date=source_as_of_date,
                effective_date=source_effective_date,
                limit=limit,
                rank_col=rank_col,
                score_col=score_col,
                confidence_col=confidence_col,
                reason_col=reason_col,
                as_of_col=as_of_col,
                effective_col=effective_col,
                filter_reason=True,
                filter_dates=True,
            )
            if rows:
                return rows

            rows = self._query_strategy_signals(
                source_signal_run_id=source_signal_run_id,
                as_of_date=source_as_of_date,
                effective_date=source_effective_date,
                limit=limit,
                rank_col=rank_col,
                score_col=score_col,
                confidence_col=confidence_col,
                reason_col=reason_col,
                as_of_col=as_of_col,
                effective_col=effective_col,
                filter_reason=False,
                filter_dates=True,
            )
            if rows:
                return rows

        # 3) Legacy compatibility only for very old schemas without usable date
        # columns. Modern strategy_signal has as_of_date/effective_date, so normal
        # production flow should not reach this branch.
        if not as_of_col and not effective_col:
            return self._query_strategy_signals(
                source_signal_run_id=source_signal_run_id,
                as_of_date=as_of_date,
                effective_date=effective_date,
                limit=limit,
                rank_col=rank_col,
                score_col=score_col,
                confidence_col=confidence_col,
                reason_col=reason_col,
                as_of_col=as_of_col,
                effective_col=effective_col,
                filter_reason=False,
                filter_dates=False,
            )

        return []

    def _resolve_latest_signal_dates_for_run(
        self,
        *,
        source_signal_run_id: int,
        effective_date: date,
        as_of_col: str | None,
        effective_col: str | None,
    ) -> tuple[date, date] | None:
        if effective_col is None:
            return None

        select_as_of = f"{as_of_col} as source_as_of_date" if as_of_col else "null as source_as_of_date"
        group_as_of = f", {as_of_col}" if as_of_col else ""
        order_as_of = f", {as_of_col} desc" if as_of_col else ""

        row = self.session.execute(
            text(
                f"""
                select
                    {select_as_of},
                    {effective_col} as source_effective_date,
                    count(*) as row_count
                from strategy_signal
                where run_id = :run_id
                  and instrument_id is not null
                  and {effective_col} <= :effective_date
                group by {effective_col}{group_as_of}
                order by {effective_col} desc{order_as_of}
                limit 1
                """
            ),
            {
                "run_id": source_signal_run_id,
                "effective_date": effective_date,
            },
        ).mappings().first()

        if row is None:
            return None

        source_effective_date = row["source_effective_date"]
        source_as_of_date = row["source_as_of_date"] or source_effective_date
        return source_as_of_date, source_effective_date

    def _query_strategy_signals(
        self,
        source_signal_run_id: int,
        as_of_date: date,
        effective_date: date,
        limit: int,
        rank_col: str | None,
        score_col: str | None,
        confidence_col: str | None,
        reason_col: str | None,
        as_of_col: str | None,
        effective_col: str | None,
        filter_reason: bool,
        filter_dates: bool,
    ) -> list[dict]:
        select_score = f"{score_col} as score" if score_col else "null as score"
        select_reason = (
            f"{reason_col} as reason_code" if reason_col else "null as reason_code"
        )

        where_parts = ["run_id = :run_id", "instrument_id is not null"]

        params = {
            "run_id": source_signal_run_id,
            "as_of_date": as_of_date,
            "effective_date": effective_date,
            "limit": limit,
        }

        if filter_dates:
            if as_of_col:
                where_parts.append(f"{as_of_col} = :as_of_date")
            if effective_col:
                where_parts.append(f"{effective_col} = :effective_date")

        if filter_reason and reason_col:
            where_parts.append(
                f"({reason_col} = 'TOP_N_SELECTED' or {reason_col} like '%TOP_N_SELECTED%')"
            )

        order_terms: list[str] = []
        if rank_col:
            order_terms.append(f"{rank_col} asc nulls last")
        if score_col:
            order_terms.append(f"{score_col} desc nulls last")
        if confidence_col and confidence_col != score_col:
            order_terms.append(f"{confidence_col} desc nulls last")
        order_terms.extend(["instrument_id asc", "id asc"])
        order_by = ", ".join(order_terms)

        sql = text(
            f"""
            select
                id as strategy_signal_id,
                instrument_id,
                {select_score},
                {select_reason}
            from strategy_signal
            where {" and ".join(where_parts)}
            order by {order_by}
            limit :limit
            """
        )

        result = self.session.execute(sql, params).mappings().all()
        return [dict(row) for row in result]

    def _diagnose_strategy_signal(self, source_signal_run_id: int) -> dict:
        total = self.session.execute(
            text("select count(*) from strategy_signal where run_id = :run_id"),
            {"run_id": source_signal_run_id},
        ).scalar_one()

        columns = sorted(self._get_table_columns("strategy_signal"))

        return {
            "strategy_signal_count_for_run": int(total),
            "strategy_signal_columns": columns,
        }

    def _get_table_columns(self, table_name: str) -> set[str]:
        sql = text(
            """
            select column_name
            from information_schema.columns
            where table_schema = 'public'
              and table_name = :table_name
            """
        )
        rows = self.session.execute(sql, {"table_name": table_name}).all()
        return {row[0] for row in rows}

    @staticmethod
    def _pick_first_existing_column(
        columns: set[str],
        candidates: list[str],
    ) -> str | None:
        for candidate in candidates:
            if candidate in columns:
                return candidate
        return None

    @staticmethod
    def _to_decimal(value: Any) -> Decimal:
        if value is None:
            return Decimal("0")
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    @staticmethod
    def _money(value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _floor_to_lot(quantity: Decimal, lot_size: Decimal) -> Decimal:
        if lot_size <= 0:
            return quantity
        if quantity <= 0:
            return Decimal("0")
        lots = (quantity / lot_size).to_integral_value(rounding=ROUND_FLOOR)
        return lots * lot_size

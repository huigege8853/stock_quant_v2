from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

TARGET_TABLE = "trading_paper_target_position"
DECISION_TABLE = "risk_decision"


class Risk3TargetOverlayService:
    """
    M7-Risk.3 overlay engine.

    This service intentionally does not replace M7-Risk.1/2.
    It applies only exposure/switch/liquidity rules on top of a source target run,
    emits risk_decision rows, and writes a new adjusted target run.
    """

    def __init__(self, session: Session):
        self.session = session

    def apply(
        self,
        *,
        source_target_run_id: int,
        adjusted_target_run_id: int,
        risk_run_id: int,
        portfolio_id: int,
        risk_profile_code: str,
        as_of_date: date | None,
        effective_date: date | None,
        current_position_run_id: int | None,
        replace_existing: bool,
    ) -> dict[str, Any]:
        profile = self._load_profile(risk_profile_code)
        rules = self._load_rules(int(profile["id"]))

        source_rows = self._load_source_targets(
            source_target_run_id=source_target_run_id,
            portfolio_id=portfolio_id,
            effective_date=effective_date,
        )
        if not source_rows:
            raise RuntimeError(
                f"No source target rows: run_id={source_target_run_id}, portfolio_id={portfolio_id}"
            )

        effective_date = effective_date or source_rows[0]["effective_date"]
        as_of_date = as_of_date or source_rows[0]["as_of_date"]

        if replace_existing:
            self._delete_existing(
                risk_run_id=risk_run_id,
                adjusted_target_run_id=adjusted_target_run_id,
                portfolio_id=portfolio_id,
            )
        else:
            existing = self._count_adjusted_targets(
                adjusted_target_run_id=adjusted_target_run_id,
                portfolio_id=portfolio_id,
            )
            if existing > 0:
                raise RuntimeError(
                    f"adjusted_target_run_id={adjusted_target_run_id} already has rows; "
                    "use a new run id or set M7_RISK3_REPLACE_EXISTING=true if not consumed by trading orders."
                )

        current_positions = self._load_current_positions(
            current_position_run_id=current_position_run_id,
            portfolio_id=portfolio_id,
        )

        industry_map = self._load_industry_map(
            instrument_ids=[int(r["instrument_id"]) for r in source_rows],
            as_of_date=as_of_date,
        )
        industry_totals = self._compute_industry_totals(source_rows, industry_map)

        states: dict[int, dict[str, Any]] = {}
        decision_stats = {"PASS": 0, "WARN": 0, "REJECT": 0, "ADJUST": 0}

        for row in source_rows:
            source_id = int(row["id"])
            states[source_id] = self._initial_state(row)

        for row in source_rows:
            source_id = int(row["id"])
            state = states[source_id]

            for rule in rules:
                before = dict(state)
                decision = self._apply_rule(
                    rule=rule,
                    source=row,
                    state=state,
                    as_of_date=as_of_date,
                    effective_date=effective_date,
                    current_positions=current_positions,
                    industry_map=industry_map,
                    industry_totals=industry_totals,
                )
                decision_stats[decision["decision_type"]] = decision_stats.get(decision["decision_type"], 0) + 1
                self._insert_decision(
                    risk_run_id=risk_run_id,
                    portfolio_id=portfolio_id,
                    source_target_run_id=source_target_run_id,
                    adjusted_target_run_id=adjusted_target_run_id,
                    risk_profile_id=int(profile["id"]),
                    rule=rule,
                    source=row,
                    before=before,
                    after=state,
                    decision=decision,
                    decision_date=effective_date,
                )

        adjusted_count = 0
        for row in source_rows:
            adjusted_id = self._insert_adjusted_target(
                source=row,
                adjusted_target_run_id=adjusted_target_run_id,
                state=states[int(row["id"])],
                as_of_date=as_of_date,
                effective_date=effective_date,
            )
            adjusted_count += 1
            self._link_adjusted_position_id(
                risk_run_id=risk_run_id,
                portfolio_id=portfolio_id,
                source_target_run_id=source_target_run_id,
                adjusted_target_run_id=adjusted_target_run_id,
                source_target_position_id=int(row["id"]),
                adjusted_target_position_id=adjusted_id,
            )

        source_total = self._sum_target_quantity(source_target_run_id, portfolio_id)
        adjusted_total = self._sum_target_quantity(adjusted_target_run_id, portfolio_id)
        decision_count = sum(decision_stats.values())

        return {
            "risk_run_id": risk_run_id,
            "source_target_run_id": source_target_run_id,
            "adjusted_target_run_id": adjusted_target_run_id,
            "portfolio_id": portfolio_id,
            "risk_profile_code": risk_profile_code,
            "source_target_count": len(source_rows),
            "adjusted_target_count": adjusted_count,
            "decision_count": decision_count,
            "pass_count": decision_stats.get("PASS", 0),
            "warn_count": decision_stats.get("WARN", 0),
            "reject_count": decision_stats.get("REJECT", 0),
            "adjust_count": decision_stats.get("ADJUST", 0),
            "source_target_quantity_total": str(source_total),
            "adjusted_target_quantity_total": str(adjusted_total),
            "diagnostics": {
                "profile_id": int(profile["id"]),
                "rule_codes": [r["rule_code"] for r in rules],
                "industry_coverage_count": sum(1 for v in industry_map.values() if v),
                "industry_missing_count": sum(1 for v in industry_map.values() if not v),
            },
            "status": "SUCCESS",
        }

    def _apply_rule(
        self,
        *,
        rule: dict[str, Any],
        source: dict[str, Any],
        state: dict[str, Any],
        as_of_date: date,
        effective_date: date,
        current_positions: dict[int, dict[str, Any]],
        industry_map: dict[int, str | None],
        industry_totals: dict[str, Decimal],
    ) -> dict[str, str]:
        code = rule["rule_code"]
        params = rule.get("params_json") or {}
        action = str(rule.get("action") or "WARN").upper()

        if state.get("rejected"):
            return self._decision("PASS", code + "_SKIPPED_AFTER_REJECT", "NO_CHANGE", "already rejected")

        if code == "R007_INDUSTRY_MAX_WEIGHT":
            return self._apply_industry_max_weight(
                source=source,
                state=state,
                params=params,
                action=action,
                industry_map=industry_map,
                industry_totals=industry_totals,
                as_of_date=as_of_date,
            )

        if code == "R009_MARKET_RISK_SWITCH":
            return self._apply_market_risk_switch(
                source=source,
                state=state,
                params=params,
                current_positions=current_positions,
                as_of_date=as_of_date,
            )

        if code == "R011_LIQUIDITY_FILTER":
            return self._apply_liquidity_filter(
                source=source,
                state=state,
                params=params,
                action=action,
                as_of_date=as_of_date,
            )

        return self._decision("WARN", "UNKNOWN_RISK3_RULE", "NO_CHANGE", f"unknown rule_code={code}")

    def _apply_industry_max_weight(
        self,
        *,
        source: dict[str, Any],
        state: dict[str, Any],
        params: dict[str, Any],
        action: str,
        industry_map: dict[int, str | None],
        industry_totals: dict[str, Decimal],
        as_of_date: date,
    ) -> dict[str, str]:
        instrument_id = int(source["instrument_id"])
        industry_code = industry_map.get(instrument_id)
        missing_action = str(params.get("missing_industry_action", "WARN")).upper()

        if not industry_code:
            if missing_action == "REJECT" or action == "REJECT":
                self._zero_state(state, "R007_MISSING_INDUSTRY")
                return self._decision("REJECT", "R007_MISSING_INDUSTRY", "SET_TARGET_ZERO", "missing industry classification")
            return self._decision("WARN", "R007_MISSING_INDUSTRY", "NO_CHANGE", "missing industry classification")

        max_weight = self._to_decimal(params.get("max_industry_weight", "0.25"))
        industry_weight = industry_totals.get(industry_code, Decimal("0"))
        if max_weight <= 0 or industry_weight <= max_weight:
            return self._decision("PASS", "R007_INDUSTRY_MAX_WEIGHT", "NO_CHANGE", f"industry={industry_code}; weight={industry_weight}")

        if action == "WARN":
            return self._decision("WARN", "R007_INDUSTRY_OVER_LIMIT", "NO_CHANGE", f"industry={industry_code}; weight={industry_weight}; max={max_weight}")

        scale = max_weight / industry_weight
        lot_size = self._to_decimal(params.get("lot_size", "100"))
        price = self._resolve_adjust_price(source=source, state=state, as_of_date=as_of_date)
        old_qty = self._to_decimal(state["target_quantity"])
        new_qty = self._floor_to_lot(old_qty * scale, lot_size)
        state["target_quantity"] = new_qty
        state["target_amount"] = self._money(new_qty * price)
        state["target_weight"] = self._money_weight(self._to_decimal(state["target_weight"]) * scale)
        state["status"] = "RISK_ADJUSTED"
        state["status_reason"] = self._append_reason(state.get("status_reason"), "R007_INDUSTRY_OVER_LIMIT")
        return self._decision("ADJUST", "R007_INDUSTRY_OVER_LIMIT", "SCALE_INDUSTRY_EXPOSURE", f"industry={industry_code}; scale={scale}")

    def _apply_market_risk_switch(
        self,
        *,
        source: dict[str, Any],
        state: dict[str, Any],
        params: dict[str, Any],
        current_positions: dict[int, dict[str, Any]],
        as_of_date: date,
    ) -> dict[str, str]:
        mode = str(params.get("market_risk_mode", "NORMAL")).upper()
        if mode in {"NORMAL", "OFF"}:
            return self._decision("PASS", "R009_MARKET_RISK_NORMAL", "NO_CHANGE", "market risk mode normal")

        instrument_id = int(source["instrument_id"])
        current_qty = self._to_decimal(current_positions.get(instrument_id, {}).get("quantity"))
        target_qty = self._to_decimal(state["target_quantity"])
        lot_size = self._to_decimal(params.get("lot_size", "100"))
        price = self._resolve_adjust_price(source=source, state=state, as_of_date=as_of_date)

        if mode == "REDUCE":
            multiplier = self._to_decimal(params.get("gross_exposure_multiplier", "1.0"))
            if multiplier >= 1:
                return self._decision("PASS", "R009_MARKET_RISK_REDUCE", "NO_CHANGE", f"multiplier={multiplier}")
            new_qty = self._floor_to_lot(target_qty * multiplier, lot_size)
            state["target_quantity"] = new_qty
            state["target_amount"] = self._money(new_qty * price)
            state["target_weight"] = self._money_weight(self._to_decimal(state["target_weight"]) * multiplier)
            state["status"] = "RISK_ADJUSTED"
            state["status_reason"] = self._append_reason(state.get("status_reason"), "R009_MARKET_RISK_REDUCE")
            return self._decision("ADJUST", "R009_MARKET_RISK_REDUCE", "SCALE_GROSS_EXPOSURE", f"multiplier={multiplier}")

        if mode == "NO_BUY":
            if target_qty > current_qty:
                new_qty = current_qty
                state["target_quantity"] = new_qty
                state["target_amount"] = self._money(new_qty * price)
                if target_qty > 0:
                    state["target_weight"] = self._money_weight(self._to_decimal(state["target_weight"]) * (new_qty / target_qty))
                state["status"] = "RISK_ADJUSTED"
                state["status_reason"] = self._append_reason(state.get("status_reason"), "R009_MARKET_RISK_NO_BUY")
                return self._decision("ADJUST", "R009_MARKET_RISK_NO_BUY", "BLOCK_NEW_BUY", "market risk blocks new buys")
            return self._decision("PASS", "R009_MARKET_RISK_NO_BUY", "NO_CHANGE", "no new buy")

        if mode == "LIQUIDATE":
            self._zero_state(state, "R009_MARKET_RISK_LIQUIDATE")
            return self._decision("REJECT", "R009_MARKET_RISK_LIQUIDATE", "SET_TARGET_ZERO", "market risk liquidation mode")

        return self._decision("WARN", "R009_UNKNOWN_MARKET_RISK_MODE", "NO_CHANGE", f"unknown mode={mode}")

    def _apply_liquidity_filter(
        self,
        *,
        source: dict[str, Any],
        state: dict[str, Any],
        params: dict[str, Any],
        action: str,
        as_of_date: date,
    ) -> dict[str, str]:
        instrument_id = int(source["instrument_id"])
        liquidity = self._resolve_liquidity(instrument_id=instrument_id, as_of_date=as_of_date)
        missing_action = str(params.get("missing_liquidity_action", "WARN")).upper()

        if liquidity is None:
            if missing_action == "REJECT" or action == "REJECT":
                self._zero_state(state, "R011_MISSING_LIQUIDITY")
                return self._decision("REJECT", "R011_MISSING_LIQUIDITY", "SET_TARGET_ZERO", "missing liquidity")
            return self._decision("WARN", "R011_MISSING_LIQUIDITY", "NO_CHANGE", "missing liquidity")

        turnover = self._to_decimal(liquidity.get("turnover_amount"))
        min_turnover = self._to_decimal(params.get("min_turnover_amount", "0"))
        max_participation = self._to_decimal(params.get("max_participation_rate", "0.10"))

        if turnover <= 0:
            if missing_action == "REJECT" or action == "REJECT":
                self._zero_state(state, "R011_ZERO_LIQUIDITY")
                return self._decision("REJECT", "R011_ZERO_LIQUIDITY", "SET_TARGET_ZERO", "zero liquidity")
            return self._decision("WARN", "R011_ZERO_LIQUIDITY", "NO_CHANGE", "zero liquidity")

        if min_turnover > 0 and turnover < min_turnover:
            if action == "REJECT":
                self._zero_state(state, "R011_LOW_LIQUIDITY")
                return self._decision("REJECT", "R011_LOW_LIQUIDITY", "SET_TARGET_ZERO", f"turnover={turnover}; min={min_turnover}")
            if action == "WARN":
                return self._decision("WARN", "R011_LOW_LIQUIDITY", "NO_CHANGE", f"turnover={turnover}; min={min_turnover}")

        target_amount = self._to_decimal(state["target_amount"])
        cap_amount = self._money(turnover * max_participation)
        if max_participation > 0 and target_amount > cap_amount:
            if action == "WARN":
                return self._decision("WARN", "R011_PARTICIPATION_OVER_CAP", "NO_CHANGE", f"target_amount={target_amount}; cap={cap_amount}")

            lot_size = self._to_decimal(params.get("lot_size", "100"))
            price = self._resolve_adjust_price(source=source, state=state, as_of_date=as_of_date)
            new_qty = self._floor_to_lot(cap_amount / price, lot_size)
            state["target_quantity"] = new_qty
            state["target_amount"] = self._money(new_qty * price)
            old_amount = self._to_decimal(source.get("target_amount"))
            if old_amount > 0:
                state["target_weight"] = self._money_weight(self._to_decimal(source.get("target_weight")) * (state["target_amount"] / old_amount))
            state["status"] = "RISK_ADJUSTED"
            state["status_reason"] = self._append_reason(state.get("status_reason"), "R011_PARTICIPATION_OVER_CAP")
            return self._decision("ADJUST", "R011_PARTICIPATION_OVER_CAP", "CAP_BY_LIQUIDITY", f"target_amount={target_amount}; cap={cap_amount}")

        return self._decision("PASS", "R011_LIQUIDITY_FILTER", "NO_CHANGE", f"turnover={turnover}")

    def _load_profile(self, profile_code: str) -> dict[str, Any]:
        row = self.session.execute(
            text(
                """
                select *
                from risk_profile
                where profile_code = :profile_code
                  and enabled = true
                limit 1
                """
            ),
            {"profile_code": profile_code},
        ).mappings().first()
        if row is None:
            raise RuntimeError(f"risk profile not found or disabled: {profile_code}")
        return dict(row)

    def _load_rules(self, profile_id: int) -> list[dict[str, Any]]:
        rows = self.session.execute(
            text(
                """
                select
                    rpr.id as profile_rule_id,
                    r.id as rule_id,
                    r.rule_code,
                    r.rule_name,
                    r.rule_type,
                    rpr.action,
                    coalesce(rpr.params_json, r.default_params_json, '{}'::json) as params_json,
                    rpr.priority
                from risk_profile_rule rpr
                join risk_rule r on r.id = rpr.rule_id
                where rpr.profile_id = :profile_id
                  and rpr.enabled = true
                  and r.enabled = true
                  and r.rule_code in (
                      'R007_INDUSTRY_MAX_WEIGHT',
                      'R009_MARKET_RISK_SWITCH',
                      'R011_LIQUIDITY_FILTER'
                  )
                order by rpr.priority asc, r.id asc
                """
            ),
            {"profile_id": profile_id},
        ).mappings().all()
        return [dict(r) for r in rows]

    def _load_source_targets(self, *, source_target_run_id: int, portfolio_id: int, effective_date: date | None) -> list[dict[str, Any]]:
        params = {"source_target_run_id": source_target_run_id, "portfolio_id": portfolio_id}
        date_filter = ""
        if effective_date is not None:
            date_filter = " and effective_date = :effective_date"
            params["effective_date"] = effective_date

        rows = self.session.execute(
            text(
                f"""
                select *
                from {TARGET_TABLE}
                where run_id = :source_target_run_id
                  and portfolio_id = :portfolio_id
                  {date_filter}
                order by coalesce(rank_no, 999999), instrument_id
                """
            ),
            params,
        ).mappings().all()
        return [dict(r) for r in rows]

    def _delete_existing(self, *, risk_run_id: int, adjusted_target_run_id: int, portfolio_id: int) -> None:
        self.session.execute(
            text(
                f"""
                delete from {DECISION_TABLE}
                where portfolio_id = :portfolio_id
                  and (run_id = :risk_run_id or adjusted_target_run_id = :adjusted_target_run_id)
                """
            ),
            {"portfolio_id": portfolio_id, "risk_run_id": risk_run_id, "adjusted_target_run_id": adjusted_target_run_id},
        )
        self.session.execute(
            text(
                f"""
                delete from {TARGET_TABLE}
                where run_id = :adjusted_target_run_id
                  and portfolio_id = :portfolio_id
                """
            ),
            {"portfolio_id": portfolio_id, "adjusted_target_run_id": adjusted_target_run_id},
        )

    def _count_adjusted_targets(self, *, adjusted_target_run_id: int, portfolio_id: int) -> int:
        return int(
            self.session.execute(
                text(
                    f"""
                    select count(*)
                    from {TARGET_TABLE}
                    where run_id = :adjusted_target_run_id
                      and portfolio_id = :portfolio_id
                    """
                ),
                {"adjusted_target_run_id": adjusted_target_run_id, "portfolio_id": portfolio_id},
            ).scalar_one()
        )

    def _load_current_positions(self, *, current_position_run_id: int | None, portfolio_id: int) -> dict[int, dict[str, Any]]:
        if not current_position_run_id:
            return {}
        rows = self.session.execute(
            text(
                """
                select *
                from trading_paper_position
                where run_id = :run_id
                  and portfolio_id = :portfolio_id
                """
            ),
            {"run_id": current_position_run_id, "portfolio_id": portfolio_id},
        ).mappings().all()
        return {int(r["instrument_id"]): dict(r) for r in rows}

    def _load_industry_map(self, *, instrument_ids: list[int], as_of_date: date) -> dict[int, str | None]:
        out = {iid: None for iid in instrument_ids}
        if not self._table_exists("instrument_tag") or not self._table_exists("tag"):
            return out

        tag_cols = self._get_columns("tag")
        code_col = self._pick_first_existing_column(tag_cols, ["tag_code", "code", "name", "tag_name"])
        type_col = self._pick_first_existing_column(tag_cols, ["tag_type", "type", "category", "tag_category"])
        if code_col is None:
            return out

        industry_filter = ""
        if type_col is not None:
            industry_filter = f" and lower(coalesce(t.{type_col}, '')) in ('industry', 'sw_industry', '申万行业', 'industry_level1')"

        rows = self.session.execute(
            text(
                f"""
                select it.instrument_id, t.{code_col} as industry_code
                from instrument_tag it
                join tag t on t.id = it.tag_id
                where it.instrument_id = any(:instrument_ids)
                  and it.effective_from <= :as_of_date
                  and (it.effective_to is null or it.effective_to >= :as_of_date)
                  {industry_filter}
                order by it.instrument_id, it.effective_from desc
                """
            ),
            {"instrument_ids": instrument_ids, "as_of_date": as_of_date},
        ).mappings().all()

        for row in rows:
            iid = int(row["instrument_id"])
            if out.get(iid) is None:
                out[iid] = str(row["industry_code"])
        return out

    def _compute_industry_totals(self, rows: list[dict[str, Any]], industry_map: dict[int, str | None]) -> dict[str, Decimal]:
        totals: dict[str, Decimal] = {}
        for row in rows:
            industry = industry_map.get(int(row["instrument_id"]))
            if not industry:
                continue
            totals[industry] = totals.get(industry, Decimal("0")) + self._to_decimal(row.get("target_weight"))
        return totals

    def _resolve_liquidity(self, *, instrument_id: int, as_of_date: date) -> dict[str, Any] | None:
        if not self._table_exists("core_daily_bar"):
            return None
        cols = self._get_columns("core_daily_bar")
        date_col = self._pick_first_existing_column(cols, ["trade_date", "bar_date", "date"])
        amount_col = self._pick_first_existing_column(cols, ["turnover_amount", "amount", "trade_amount", "money", "value"])
        volume_col = self._pick_first_existing_column(cols, ["volume", "vol", "trade_volume"])
        close_col = self._pick_first_existing_column(cols, ["close_price", "close", "adj_close", "close_adj"])
        if date_col is None:
            return None

        select_amount = "null"
        if amount_col:
            select_amount = amount_col
        elif volume_col and close_col:
            select_amount = f"({volume_col} * {close_col})"

        row = self.session.execute(
            text(
                f"""
                select
                    {date_col} as trade_date,
                    {select_amount} as turnover_amount
                from core_daily_bar
                where instrument_id = :instrument_id
                  and {date_col} <= :as_of_date
                order by {date_col} desc
                limit 1
                """
            ),
            {"instrument_id": instrument_id, "as_of_date": as_of_date},
        ).mappings().first()
        return dict(row) if row is not None else None

    def _resolve_adjust_price(self, *, source: dict[str, Any], state: dict[str, Any], as_of_date: date) -> Decimal:
        amount = self._to_decimal(state.get("target_amount"))
        qty = self._to_decimal(state.get("target_quantity"))
        if amount > 0 and qty > 0:
            return amount / qty

        if self._table_exists("core_daily_bar"):
            cols = self._get_columns("core_daily_bar")
            date_col = self._pick_first_existing_column(cols, ["trade_date", "bar_date", "date"])
            price_col = self._pick_first_existing_column(cols, ["close_price", "close", "open_price", "open"])
            if date_col and price_col:
                row = self.session.execute(
                    text(
                        f"""
                        select {price_col} as price
                        from core_daily_bar
                        where instrument_id = :instrument_id
                          and {date_col} <= :as_of_date
                          and coalesce({price_col}, 0) > 0
                        order by {date_col} desc
                        limit 1
                        """
                    ),
                    {"instrument_id": int(source["instrument_id"]), "as_of_date": as_of_date},
                ).mappings().first()
                if row is not None:
                    price = self._to_decimal(row["price"])
                    if price > 0:
                        return price

        raise RuntimeError(f"Cannot resolve adjustment price for instrument_id={source.get('instrument_id')}")

    def _initial_state(self, source: dict[str, Any]) -> dict[str, Any]:
        return {
            "target_weight": self._to_decimal(source.get("target_weight")),
            "target_amount": self._to_decimal(source.get("target_amount")),
            "target_quantity": self._to_decimal(source.get("target_quantity")),
            "status": "RISK3_PASSED",
            "status_reason": source.get("status_reason") or "",
            "rejected": False,
        }

    def _zero_state(self, state: dict[str, Any], reason: str) -> None:
        state["target_weight"] = Decimal("0")
        state["target_amount"] = Decimal("0")
        state["target_quantity"] = Decimal("0")
        state["status"] = "REJECTED"
        state["status_reason"] = self._append_reason(state.get("status_reason"), reason)
        state["rejected"] = True

    def _insert_decision(
        self,
        *,
        risk_run_id: int,
        portfolio_id: int,
        source_target_run_id: int,
        adjusted_target_run_id: int,
        risk_profile_id: int,
        rule: dict[str, Any],
        source: dict[str, Any],
        before: dict[str, Any],
        after: dict[str, Any],
        decision: dict[str, str],
        decision_date: date,
    ) -> None:
        self.session.execute(
            text(
                f"""
                insert into {DECISION_TABLE} (
                    run_id, portfolio_id, source_target_run_id, adjusted_target_run_id,
                    risk_profile_id, risk_rule_id, source_target_position_id,
                    adjusted_target_position_id, instrument_id, decision_date,
                    decision_type, reason_code, action_taken,
                    before_target_weight, after_target_weight,
                    before_target_quantity, after_target_quantity,
                    before_target_amount, after_target_amount,
                    message, payload_json, created_at
                )
                values (
                    :run_id, :portfolio_id, :source_target_run_id, :adjusted_target_run_id,
                    :risk_profile_id, :risk_rule_id, :source_target_position_id,
                    null, :instrument_id, :decision_date,
                    :decision_type, :reason_code, :action_taken,
                    :before_target_weight, :after_target_weight,
                    :before_target_quantity, :after_target_quantity,
                    :before_target_amount, :after_target_amount,
                    :message, cast(:payload_json as jsonb), now()
                )
                """
            ),
            {
                "run_id": risk_run_id,
                "portfolio_id": portfolio_id,
                "source_target_run_id": source_target_run_id,
                "adjusted_target_run_id": adjusted_target_run_id,
                "risk_profile_id": risk_profile_id,
                "risk_rule_id": rule.get("rule_id"),
                "source_target_position_id": source.get("id"),
                "instrument_id": source.get("instrument_id"),
                "decision_date": decision_date,
                "decision_type": decision["decision_type"],
                "reason_code": decision["reason_code"],
                "action_taken": decision["action_taken"],
                "before_target_weight": before.get("target_weight"),
                "after_target_weight": after.get("target_weight"),
                "before_target_quantity": before.get("target_quantity"),
                "after_target_quantity": after.get("target_quantity"),
                "before_target_amount": before.get("target_amount"),
                "after_target_amount": after.get("target_amount"),
                "message": decision["message"],
                "payload_json": json.dumps(
                    {
                        "rule_code": rule.get("rule_code"),
                        "rule_name": rule.get("rule_name"),
                        "rule_type": rule.get("rule_type"),
                        "params_json": rule.get("params_json"),
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            },
        )

    def _insert_adjusted_target(self, *, source: dict[str, Any], adjusted_target_run_id: int, state: dict[str, Any], as_of_date: date, effective_date: date) -> int:
        now = datetime.utcnow()
        return int(
            self.session.execute(
                text(
                    f"""
                    insert into {TARGET_TABLE} (
                        run_id, portfolio_id, source_signal_run_id, source_screen_request_id,
                        strategy_signal_id, as_of_date, effective_date, instrument_id,
                        target_side, target_weight, target_amount, target_quantity,
                        rank_no, score, reason_code, target_source, construction_mode,
                        status, status_reason, created_at, updated_at
                    )
                    values (
                        :run_id, :portfolio_id, :source_signal_run_id, :source_screen_request_id,
                        :strategy_signal_id, :as_of_date, :effective_date, :instrument_id,
                        :target_side, :target_weight, :target_amount, :target_quantity,
                        :rank_no, :score, :reason_code, :target_source, :construction_mode,
                        :status, :status_reason, :created_at, :updated_at
                    )
                    returning id
                    """
                ),
                {
                    "run_id": adjusted_target_run_id,
                    "portfolio_id": source["portfolio_id"],
                    "source_signal_run_id": source["source_signal_run_id"],
                    "source_screen_request_id": source.get("source_screen_request_id"),
                    "strategy_signal_id": source.get("strategy_signal_id"),
                    "as_of_date": as_of_date,
                    "effective_date": effective_date,
                    "instrument_id": source["instrument_id"],
                    "target_side": source.get("target_side") or "LONG",
                    "target_weight": state["target_weight"],
                    "target_amount": state["target_amount"],
                    "target_quantity": state["target_quantity"],
                    "rank_no": source.get("rank_no"),
                    "score": source.get("score"),
                    "reason_code": self._append_reason(source.get("reason_code"), "RISK3_APPLIED"),
                    "target_source": "RISK3_ADJUSTED_TARGET",
                    "construction_mode": source.get("construction_mode") or "EQUAL_WEIGHT_SELECTED",
                    "status": state["status"],
                    "status_reason": (state.get("status_reason") or "")[:255],
                    "created_at": now,
                    "updated_at": now,
                },
            ).scalar_one()
        )

    def _link_adjusted_position_id(
        self,
        *,
        risk_run_id: int,
        portfolio_id: int,
        source_target_run_id: int,
        adjusted_target_run_id: int,
        source_target_position_id: int,
        adjusted_target_position_id: int,
    ) -> None:
        self.session.execute(
            text(
                f"""
                update {DECISION_TABLE}
                set adjusted_target_position_id = :adjusted_target_position_id
                where run_id = :risk_run_id
                  and portfolio_id = :portfolio_id
                  and source_target_run_id = :source_target_run_id
                  and adjusted_target_run_id = :adjusted_target_run_id
                  and source_target_position_id = :source_target_position_id
                """
            ),
            {
                "adjusted_target_position_id": adjusted_target_position_id,
                "risk_run_id": risk_run_id,
                "portfolio_id": portfolio_id,
                "source_target_run_id": source_target_run_id,
                "adjusted_target_run_id": adjusted_target_run_id,
                "source_target_position_id": source_target_position_id,
            },
        )

    def _sum_target_quantity(self, run_id: int, portfolio_id: int) -> Decimal:
        return self._to_decimal(
            self.session.execute(
                text(
                    f"""
                    select coalesce(sum(target_quantity), 0)
                    from {TARGET_TABLE}
                    where run_id = :run_id
                      and portfolio_id = :portfolio_id
                    """
                ),
                {"run_id": run_id, "portfolio_id": portfolio_id},
            ).scalar_one()
        )

    def _decision(self, decision_type: str, reason_code: str, action_taken: str, message: str) -> dict[str, str]:
        return {
            "decision_type": decision_type,
            "reason_code": reason_code,
            "action_taken": action_taken,
            "message": message,
        }

    def _table_exists(self, table_name: str) -> bool:
        return self.session.execute(
            text(
                """
                select 1
                from information_schema.tables
                where table_schema = 'public'
                  and table_name = :table_name
                """
            ),
            {"table_name": table_name},
        ).scalar_one_or_none() is not None

    def _get_columns(self, table_name: str) -> set[str]:
        rows = self.session.execute(
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

    @staticmethod
    def _pick_first_existing_column(columns: set[str], candidates: list[str]) -> str | None:
        for c in candidates:
            if c in columns:
                return c
        return None

    @staticmethod
    def _append_reason(current: str | None, reason: str) -> str:
        if not current:
            return reason
        if reason in current:
            return current
        return f"{current};{reason}"

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
    def _money_weight(value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.0000000001"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _floor_to_lot(quantity: Decimal, lot_size: Decimal) -> Decimal:
        if lot_size <= 0 or quantity <= 0:
            return Decimal("0")
        lots = (quantity / lot_size).to_integral_value(rounding=ROUND_FLOOR)
        return lots * lot_size

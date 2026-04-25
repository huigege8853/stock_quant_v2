from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from stock_quant_v2.risk_domain.dto.risk import (
    ApplyRiskToTargetRequestDTO,
    ApplyRiskToTargetResultDTO,
)


TARGET_TABLE = "trading_paper_target_position"
DECISION_TABLE = "risk_decision"


class RiskTargetService:
    """
    M7-Risk.1: apply risk profile to a target_position run.

    Design:
    - strategy_signal is immutable;
    - source target_position run is immutable;
    - risk writes decisions to risk_decision;
    - risk writes a new adjusted target_position run;
    - trading rebalance consumes adjusted_target_run_id.
    """

    def __init__(self, session: Session):
        self.session = session

    def apply_risk_to_target(
        self,
        request: ApplyRiskToTargetRequestDTO,
    ) -> ApplyRiskToTargetResultDTO:
        profile = self._load_profile(request.risk_profile_code)
        rules = self._load_profile_rules(profile_id=int(profile["id"]))

        source_rows = self._load_source_targets(
            source_target_run_id=request.source_target_run_id,
            portfolio_id=request.portfolio_id,
            effective_date=request.effective_date,
        )
        if not source_rows:
            raise RuntimeError(
                "No source target_position rows found: "
                f"run_id={request.source_target_run_id}, portfolio_id={request.portfolio_id}"
            )

        effective_date = request.effective_date or source_rows[0]["effective_date"]
        as_of_date = request.as_of_date or source_rows[0]["as_of_date"]

        if request.replace_existing:
            self._delete_existing(
                adjusted_target_run_id=request.adjusted_target_run_id,
                risk_run_id=request.risk_run_id,
                portfolio_id=request.portfolio_id,
            )
        else:
            existing = self._count_adjusted_targets(
                adjusted_target_run_id=request.adjusted_target_run_id,
                portfolio_id=request.portfolio_id,
            )
            if existing > 0:
                raise RuntimeError(
                    "Adjusted target run already has rows. "
                    f"adjusted_target_run_id={request.adjusted_target_run_id}, "
                    f"portfolio_id={request.portfolio_id}. "
                    "Set M7_RISK_REPLACE_EXISTING=true to rerun."
                )

        current_positions = self._load_current_positions(
            current_position_run_id=request.current_position_run_id,
            portfolio_id=request.portfolio_id,
        )

        ordered_source = sorted(
            source_rows,
            key=lambda r: (
                r.get("rank_no") if r.get("rank_no") is not None else 10**9,
                -self._to_decimal(r.get("score")),
                r.get("instrument_id"),
            ),
        )

        adjusted_count = 0
        decision_stats = {
            "PASS": 0,
            "WARN": 0,
            "REJECT": 0,
            "ADJUST": 0,
        }
        diagnostics: dict[str, Any] = {
            "profile_id": int(profile["id"]),
            "rule_count": len(rules),
            "rule_codes": [r["rule_code"] for r in rules],
        }

        for ordinal, source in enumerate(ordered_source, start=1):
            state = self._initial_state(source)
            source_qty = self._to_decimal(source.get("target_quantity"))
            source_weight = self._to_decimal(source.get("target_weight"))
            source_amount = self._to_decimal(source.get("target_amount"))

            for rule in rules:
                before = dict(state)
                decision = self._apply_rule(
                    rule=rule,
                    state=state,
                    source=source,
                    ordinal=ordinal,
                    effective_date=effective_date,
                    as_of_date=as_of_date,
                    current_positions=current_positions,
                )
                decision_stats[decision["decision_type"]] = (
                    decision_stats.get(decision["decision_type"], 0) + 1
                )
                self._insert_decision(
                    request=request,
                    profile_id=int(profile["id"]),
                    rule=rule,
                    source=source,
                    before=before,
                    after=state,
                    decision=decision,
                    decision_date=effective_date,
                )

            adjusted_id = self._insert_adjusted_target(
                source=source,
                adjusted_target_run_id=request.adjusted_target_run_id,
                state=state,
                effective_date=effective_date,
                as_of_date=as_of_date,
            )
            adjusted_count += 1

            self._link_adjusted_position_id(
                request=request,
                source_target_position_id=int(source["id"]),
                adjusted_target_position_id=adjusted_id,
            )

        source_total = self._sum_target_quantity(
            run_id=request.source_target_run_id,
            portfolio_id=request.portfolio_id,
        )
        adjusted_total = self._sum_target_quantity(
            run_id=request.adjusted_target_run_id,
            portfolio_id=request.portfolio_id,
        )
        decision_count = sum(decision_stats.values())

        return ApplyRiskToTargetResultDTO(
            risk_run_id=request.risk_run_id,
            source_target_run_id=request.source_target_run_id,
            adjusted_target_run_id=request.adjusted_target_run_id,
            portfolio_id=request.portfolio_id,
            risk_profile_code=request.risk_profile_code,
            source_target_count=len(source_rows),
            adjusted_target_count=adjusted_count,
            decision_count=decision_count,
            pass_count=decision_stats.get("PASS", 0),
            warn_count=decision_stats.get("WARN", 0),
            reject_count=decision_stats.get("REJECT", 0),
            adjust_count=decision_stats.get("ADJUST", 0),
            source_target_quantity_total=str(source_total),
            adjusted_target_quantity_total=str(adjusted_total),
            status="SUCCESS",
            diagnostics=diagnostics,
        )

    def _apply_rule(
        self,
        *,
        rule: dict[str, Any],
        state: dict[str, Any],
        source: dict[str, Any],
        ordinal: int,
        effective_date: date,
        as_of_date: date,
        current_positions: dict[int, dict[str, Any]],
    ) -> dict[str, Any]:
        code = rule["rule_code"]
        params = rule.get("params_json") or {}

        if state["rejected"]:
            return self._decision("PASS", code + "_SKIPPED_AFTER_REJECT", "NO_CHANGE", "already rejected")

        if code == "R001_MAX_POSITION_COUNT":
            max_count = int(params.get("max_position_count", 30))
            if ordinal > max_count:
                state["target_weight"] = Decimal("0")
                state["target_amount"] = Decimal("0")
                state["target_quantity"] = Decimal("0")
                state["status"] = "REJECTED"
                state["status_reason"] = self._append_reason(state["status_reason"], "R001_MAX_POSITION_COUNT")
                state["rejected"] = True
                return self._decision("REJECT", "R001_MAX_POSITION_COUNT", "SET_TARGET_ZERO", f"rank ordinal {ordinal} > max_position_count {max_count}")
            return self._decision("PASS", "R001_MAX_POSITION_COUNT", "NO_CHANGE", f"rank ordinal {ordinal} <= max_position_count {max_count}")

        if code == "R002_MAX_SINGLE_POSITION_WEIGHT":
            max_weight = self._to_decimal(params.get("max_weight", "0.05"))
            if self._to_decimal(state["target_weight"]) > max_weight:
                price = self._resolve_price_for_adjustment(
                    instrument_id=int(source["instrument_id"]),
                    price_date=as_of_date,
                    fallback_amount=self._to_decimal(source.get("target_amount")),
                    fallback_quantity=self._to_decimal(source.get("target_quantity")),
                )
                inferred_capital = self._infer_total_capital(source)
                lot_size = self._to_decimal(params.get("lot_size", "100"))
                new_amount = self._money(inferred_capital * max_weight)
                new_qty = self._floor_to_lot(new_amount / price, lot_size)
                state["target_weight"] = max_weight
                state["target_quantity"] = new_qty
                state["target_amount"] = self._money(new_qty * price)
                state["status"] = "RISK_ADJUSTED"
                state["status_reason"] = self._append_reason(state["status_reason"], "R002_MAX_SINGLE_POSITION_WEIGHT")
                return self._decision("ADJUST", "R002_MAX_SINGLE_POSITION_WEIGHT", "CAP_TARGET_WEIGHT", f"cap target_weight to {max_weight}")
            return self._decision("PASS", "R002_MAX_SINGLE_POSITION_WEIGHT", "NO_CHANGE", "within max single position weight")

        if code == "R003_SUSPENDED_FILTER":
            status = self._load_instrument_status(int(source["instrument_id"]), effective_date)
            if status is None:
                action = str(params.get("missing_status_action", "WARN")).upper()
                if action == "REJECT":
                    state["target_weight"] = Decimal("0")
                    state["target_amount"] = Decimal("0")
                    state["target_quantity"] = Decimal("0")
                    state["status"] = "REJECTED"
                    state["status_reason"] = self._append_reason(state["status_reason"], "R003_MISSING_STATUS")
                    state["rejected"] = True
                    return self._decision("REJECT", "R003_MISSING_STATUS", "SET_TARGET_ZERO", "missing instrument status")
                return self._decision("WARN", "R003_MISSING_STATUS", "NO_CHANGE", "missing instrument status")

            trading_status = str(status.get("trading_status") or "").upper()
            if bool(status.get("is_suspended")) or "SUSP" in trading_status or trading_status in {"HALT", "PAUSED"}:
                state["target_weight"] = Decimal("0")
                state["target_amount"] = Decimal("0")
                state["target_quantity"] = Decimal("0")
                state["status"] = "REJECTED"
                state["status_reason"] = self._append_reason(state["status_reason"], "R003_SUSPENDED_FILTER")
                state["rejected"] = True
                return self._decision("REJECT", "R003_SUSPENDED_FILTER", "SET_TARGET_ZERO", f"trading_status={trading_status}")
            return self._decision("PASS", "R003_SUSPENDED_FILTER", "NO_CHANGE", f"trading_status={trading_status}")

        if code == "R004_PRICE_LIMIT_FILTER":
            instrument_id = int(source["instrument_id"])
            price_limit = self._load_price_limit(instrument_id, effective_date)
            if price_limit is None:
                return self._decision("WARN", "R004_MISSING_PRICE_LIMIT", "NO_CHANGE", "missing price limit")
            mark_price = self._resolve_effective_or_latest_price(instrument_id, effective_date)
            if mark_price is None:
                return self._decision("WARN", "R004_MISSING_MARK_PRICE", "NO_CHANGE", "missing mark price for price limit check")

            current_qty = self._to_decimal(
                current_positions.get(instrument_id, {}).get("quantity")
            )
            target_qty = self._to_decimal(state["target_quantity"])
            delta_qty = target_qty - current_qty
            tolerance = self._to_decimal(params.get("tolerance", "0.0001"))

            up_limit = self._to_decimal(price_limit.get("up_limit"))
            down_limit = self._to_decimal(price_limit.get("down_limit"))

            if delta_qty > 0 and up_limit > 0 and mark_price >= up_limit - tolerance:
                state["target_weight"] = Decimal("0") if current_qty <= 0 else state["target_weight"]
                state["target_quantity"] = current_qty
                state["target_amount"] = self._money(current_qty * mark_price)
                state["status"] = "REJECTED" if current_qty <= 0 else "RISK_ADJUSTED"
                state["status_reason"] = self._append_reason(state["status_reason"], "R004_BUY_AT_UP_LIMIT")
                if current_qty <= 0:
                    state["rejected"] = True
                    return self._decision("REJECT", "R004_BUY_AT_UP_LIMIT", "SET_TARGET_ZERO", "buy blocked at up limit")
                return self._decision("ADJUST", "R004_BUY_AT_UP_LIMIT", "KEEP_CURRENT_QUANTITY", "increase blocked at up limit")

            if delta_qty < 0 and down_limit > 0 and mark_price <= down_limit + tolerance:
                state["target_quantity"] = current_qty
                state["target_amount"] = self._money(current_qty * mark_price)
                state["status"] = "RISK_ADJUSTED"
                state["status_reason"] = self._append_reason(state["status_reason"], "R004_SELL_AT_DOWN_LIMIT")
                return self._decision("ADJUST", "R004_SELL_AT_DOWN_LIMIT", "KEEP_CURRENT_QUANTITY", "sell blocked at down limit")

            return self._decision("PASS", "R004_PRICE_LIMIT_FILTER", "NO_CHANGE", "not at limit")

        if code == "R005_MISSING_PRICE_FILTER":
            instrument_id = int(source["instrument_id"])
            price = self._resolve_exact_effective_price(instrument_id, effective_date)
            if price is None:
                action = str(params.get("missing_effective_price_action", "WARN")).upper()
                if action == "REJECT":
                    state["target_weight"] = Decimal("0")
                    state["target_amount"] = Decimal("0")
                    state["target_quantity"] = Decimal("0")
                    state["status"] = "REJECTED"
                    state["status_reason"] = self._append_reason(state["status_reason"], "R005_MISSING_EFFECTIVE_PRICE")
                    state["rejected"] = True
                    return self._decision("REJECT", "R005_MISSING_EFFECTIVE_PRICE", "SET_TARGET_ZERO", "missing effective date price")
                return self._decision("WARN", "R005_MISSING_EFFECTIVE_PRICE", "NO_CHANGE", "missing effective date price, paper fallback may be used")
            return self._decision("PASS", "R005_MISSING_PRICE_FILTER", "NO_CHANGE", "effective date price exists")

        if code == "R006_LOT_SIZE_CHECK":
            lot_size = self._to_decimal(params.get("lot_size", "100"))
            qty = self._to_decimal(state["target_quantity"])
            if lot_size > 0 and qty % lot_size != 0:
                new_qty = self._floor_to_lot(qty, lot_size)
                price = self._resolve_price_for_adjustment(
                    instrument_id=int(source["instrument_id"]),
                    price_date=as_of_date,
                    fallback_amount=self._to_decimal(state.get("target_amount")),
                    fallback_quantity=qty,
                )
                state["target_quantity"] = new_qty
                state["target_amount"] = self._money(new_qty * price)
                state["status"] = "RISK_ADJUSTED"
                state["status_reason"] = self._append_reason(state["status_reason"], "R006_LOT_SIZE_CHECK")
                return self._decision("ADJUST", "R006_LOT_SIZE_CHECK", "FLOOR_TO_LOT", f"floor to lot_size={lot_size}")
            return self._decision("PASS", "R006_LOT_SIZE_CHECK", "NO_CHANGE", "lot size ok")

        return self._decision("WARN", "UNKNOWN_RISK_RULE", "NO_CHANGE", f"unknown rule_code={code}")

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
            raise RuntimeError(f"risk_profile not found or disabled: {profile_code}")
        return dict(row)

    def _load_profile_rules(self, *, profile_id: int) -> list[dict[str, Any]]:
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
                join risk_rule r on rpr.rule_id = r.id
                where rpr.profile_id = :profile_id
                  and rpr.enabled = true
                  and r.enabled = true
                order by rpr.priority asc, r.id asc
                """
            ),
            {"profile_id": profile_id},
        ).mappings().all()
        return [dict(row) for row in rows]

    def _load_source_targets(
        self,
        *,
        source_target_run_id: int,
        portfolio_id: int,
        effective_date: date | None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "source_target_run_id": source_target_run_id,
            "portfolio_id": portfolio_id,
        }
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
        return [dict(row) for row in rows]

    def _delete_existing(self, *, adjusted_target_run_id: int, risk_run_id: int, portfolio_id: int) -> None:
        self.session.execute(
            text(
                f"""
                delete from {DECISION_TABLE}
                where portfolio_id = :portfolio_id
                  and (run_id = :risk_run_id or adjusted_target_run_id = :adjusted_target_run_id)
                """
            ),
            {
                "portfolio_id": portfolio_id,
                "risk_run_id": risk_run_id,
                "adjusted_target_run_id": adjusted_target_run_id,
            },
        )
        self.session.execute(
            text(
                f"""
                delete from {TARGET_TABLE}
                where run_id = :adjusted_target_run_id
                  and portfolio_id = :portfolio_id
                """
            ),
            {
                "portfolio_id": portfolio_id,
                "adjusted_target_run_id": adjusted_target_run_id,
            },
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
                {
                    "adjusted_target_run_id": adjusted_target_run_id,
                    "portfolio_id": portfolio_id,
                },
            ).scalar_one()
        )

    def _load_current_positions(
        self,
        *,
        current_position_run_id: int | None,
        portfolio_id: int,
    ) -> dict[int, dict[str, Any]]:
        if not current_position_run_id:
            return {}

        rows = self.session.execute(
            text(
                """
                select *
                from trading_paper_position
                where run_id = :current_position_run_id
                  and portfolio_id = :portfolio_id
                """
            ),
            {
                "current_position_run_id": current_position_run_id,
                "portfolio_id": portfolio_id,
            },
        ).mappings().all()
        return {int(row["instrument_id"]): dict(row) for row in rows}

    def _insert_adjusted_target(
        self,
        *,
        source: dict[str, Any],
        adjusted_target_run_id: int,
        state: dict[str, Any],
        effective_date: date,
        as_of_date: date,
    ) -> int:
        now = datetime.utcnow()
        return int(
            self.session.execute(
                text(
                    f"""
                    insert into {TARGET_TABLE} (
                        run_id,
                        portfolio_id,
                        source_signal_run_id,
                        source_screen_request_id,
                        strategy_signal_id,
                        as_of_date,
                        effective_date,
                        instrument_id,
                        target_side,
                        target_weight,
                        target_amount,
                        target_quantity,
                        rank_no,
                        score,
                        reason_code,
                        target_source,
                        construction_mode,
                        status,
                        status_reason,
                        created_at,
                        updated_at
                    )
                    values (
                        :run_id,
                        :portfolio_id,
                        :source_signal_run_id,
                        :source_screen_request_id,
                        :strategy_signal_id,
                        :as_of_date,
                        :effective_date,
                        :instrument_id,
                        :target_side,
                        :target_weight,
                        :target_amount,
                        :target_quantity,
                        :rank_no,
                        :score,
                        :reason_code,
                        :target_source,
                        :construction_mode,
                        :status,
                        :status_reason,
                        :created_at,
                        :updated_at
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
                    "reason_code": self._append_reason(source.get("reason_code"), "RISK_APPLIED"),
                    "target_source": "RISK_ADJUSTED_TARGET",
                    "construction_mode": source.get("construction_mode") or "EQUAL_WEIGHT_SELECTED",
                    "status": state["status"],
                    "status_reason": state["status_reason"][:255] if state["status_reason"] else None,
                    "created_at": now,
                    "updated_at": now,
                },
            ).scalar_one()
        )

    def _insert_decision(
        self,
        *,
        request: ApplyRiskToTargetRequestDTO,
        profile_id: int,
        rule: dict[str, Any],
        source: dict[str, Any],
        before: dict[str, Any],
        after: dict[str, Any],
        decision: dict[str, Any],
        decision_date: date,
    ) -> None:
        self.session.execute(
            text(
                f"""
                insert into {DECISION_TABLE} (
                    run_id,
                    portfolio_id,
                    source_target_run_id,
                    adjusted_target_run_id,
                    risk_profile_id,
                    risk_rule_id,
                    source_target_position_id,
                    adjusted_target_position_id,
                    instrument_id,
                    decision_date,
                    decision_type,
                    reason_code,
                    action_taken,
                    before_target_weight,
                    after_target_weight,
                    before_target_quantity,
                    after_target_quantity,
                    before_target_amount,
                    after_target_amount,
                    message,
                    payload_json,
                    created_at
                )
                values (
                    :run_id,
                    :portfolio_id,
                    :source_target_run_id,
                    :adjusted_target_run_id,
                    :risk_profile_id,
                    :risk_rule_id,
                    :source_target_position_id,
                    null,
                    :instrument_id,
                    :decision_date,
                    :decision_type,
                    :reason_code,
                    :action_taken,
                    :before_target_weight,
                    :after_target_weight,
                    :before_target_quantity,
                    :after_target_quantity,
                    :before_target_amount,
                    :after_target_amount,
                    :message,
                    cast(:payload_json as jsonb),
                    now()
                )
                """
            ),
            {
                "run_id": request.risk_run_id,
                "portfolio_id": request.portfolio_id,
                "source_target_run_id": request.source_target_run_id,
                "adjusted_target_run_id": request.adjusted_target_run_id,
                "risk_profile_id": profile_id,
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

    def _link_adjusted_position_id(
        self,
        *,
        request: ApplyRiskToTargetRequestDTO,
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
                "risk_run_id": request.risk_run_id,
                "portfolio_id": request.portfolio_id,
                "source_target_run_id": request.source_target_run_id,
                "adjusted_target_run_id": request.adjusted_target_run_id,
                "source_target_position_id": source_target_position_id,
            },
        )

    def _initial_state(self, source: dict[str, Any]) -> dict[str, Any]:
        return {
            "target_weight": self._to_decimal(source.get("target_weight")),
            "target_amount": self._to_decimal(source.get("target_amount")),
            "target_quantity": self._to_decimal(source.get("target_quantity")),
            "status": "RISK_PASSED",
            "status_reason": source.get("status_reason") or "",
            "rejected": False,
        }

    def _decision(self, decision_type: str, reason_code: str, action_taken: str, message: str) -> dict[str, Any]:
        return {
            "decision_type": decision_type,
            "reason_code": reason_code,
            "action_taken": action_taken,
            "message": message,
        }

    def _load_instrument_status(self, instrument_id: int, effective_date: date) -> dict[str, Any] | None:
        row = self.session.execute(
            text(
                """
                select *
                from core_instrument_status_daily
                where instrument_id = :instrument_id
                  and trade_date = :effective_date
                limit 1
                """
            ),
            {"instrument_id": instrument_id, "effective_date": effective_date},
        ).mappings().first()
        return dict(row) if row is not None else None

    def _load_price_limit(self, instrument_id: int, effective_date: date) -> dict[str, Any] | None:
        row = self.session.execute(
            text(
                """
                select *
                from core_price_limit_daily
                where instrument_id = :instrument_id
                  and trade_date = :effective_date
                limit 1
                """
            ),
            {"instrument_id": instrument_id, "effective_date": effective_date},
        ).mappings().first()
        return dict(row) if row is not None else None

    def _resolve_exact_effective_price(self, instrument_id: int, effective_date: date) -> Decimal | None:
        cols = self._get_columns("core_daily_bar")
        price_col = self._pick_first_existing_column(cols, ["open_price", "open", "close_price", "close"])
        date_col = self._pick_first_existing_column(cols, ["trade_date", "bar_date", "date"])
        if not price_col or not date_col:
            return None
        row = self.session.execute(
            text(
                f"""
                select {price_col} as price
                from core_daily_bar
                where instrument_id = :instrument_id
                  and {date_col} = :effective_date
                  and coalesce({price_col}, 0) > 0
                limit 1
                """
            ),
            {"instrument_id": instrument_id, "effective_date": effective_date},
        ).mappings().first()
        if row is None:
            return None
        return self._to_decimal(row["price"])

    def _resolve_effective_or_latest_price(self, instrument_id: int, effective_date: date) -> Decimal | None:
        cols = self._get_columns("core_daily_bar")
        price_col = self._pick_first_existing_column(cols, ["open_price", "open", "close_price", "close"])
        date_col = self._pick_first_existing_column(cols, ["trade_date", "bar_date", "date"])
        if not price_col or not date_col:
            return None
        row = self.session.execute(
            text(
                f"""
                select {price_col} as price
                from core_daily_bar
                where instrument_id = :instrument_id
                  and {date_col} <= :effective_date
                  and coalesce({price_col}, 0) > 0
                order by {date_col} desc
                limit 1
                """
            ),
            {"instrument_id": instrument_id, "effective_date": effective_date},
        ).mappings().first()
        if row is None:
            return None
        return self._to_decimal(row["price"])

    def _resolve_price_for_adjustment(
        self,
        *,
        instrument_id: int,
        price_date: date,
        fallback_amount: Decimal,
        fallback_quantity: Decimal,
    ) -> Decimal:
        price = self._resolve_effective_or_latest_price(instrument_id, price_date)
        if price is not None and price > 0:
            return price
        if fallback_quantity > 0 and fallback_amount > 0:
            return fallback_amount / fallback_quantity
        raise RuntimeError(f"Cannot resolve risk adjustment price: instrument_id={instrument_id}, price_date={price_date}")

    def _infer_total_capital(self, source: dict[str, Any]) -> Decimal:
        weight = self._to_decimal(source.get("target_weight"))
        amount = self._to_decimal(source.get("target_amount"))
        if weight > 0 and amount > 0:
            return amount / weight
        return amount

    def _sum_target_quantity(self, *, run_id: int, portfolio_id: int) -> Decimal:
        value = self.session.execute(
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
        return self._to_decimal(value)

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
    def _floor_to_lot(quantity: Decimal, lot_size: Decimal) -> Decimal:
        if lot_size <= 0 or quantity <= 0:
            return Decimal("0")
        lots = (quantity / lot_size).to_integral_value(rounding=ROUND_FLOOR)
        return lots * lot_size

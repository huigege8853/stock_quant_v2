from __future__ import annotations

import csv
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


class M8QueryService:
    def __init__(self, session: Session):
        self.session = session

    # =========================
    # Public query methods
    # =========================

    def query_run(self, run_id: int) -> dict[str, Any]:
        run = self._one(
            """
            select
                id,
                run_uid::text as run_uid,
                run_type,
                run_name,
                status,
                trigger_type,
                parent_run_id,
                requested_at,
                started_at,
                ended_at,
                context_json,
                error_message,
                created_at,
                updated_at
            from ops_run
            where id = :run_id
            """,
            {"run_id": run_id},
        )

        steps = self._rows(
            """
            select
                id,
                run_id,
                step_code,
                step_name,
                sequence_no,
                status,
                started_at,
                ended_at,
                payload_json,
                error_message,
                created_at,
                updated_at
            from ops_run_step
            where run_id = :run_id
            order by sequence_no, id
            """,
            {"run_id": run_id},
        )

        metrics = self._rows(
            """
            select
                metric_namespace,
                metric_code,
                metric_name,
                metric_value_numeric,
                metric_value_text,
                metric_value_json,
                unit,
                period_start,
                period_end,
                dimension_type,
                dimension_key,
                sequence_no,
                created_at
            from ops_run_metric_snapshot
            where run_id = :run_id
            order by metric_namespace, sequence_no, metric_code
            """,
            {"run_id": run_id},
        )

        series = self._rows(
            """
            select
                series_namespace,
                series_code,
                trade_date,
                instrument_id,
                dimension_type,
                dimension_key,
                value_numeric,
                value_text,
                value_json,
                created_at
            from ops_run_series_snapshot
            where run_id = :run_id
            order by series_namespace, series_code, trade_date
            limit 200
            """,
            {"run_id": run_id},
        )

        artifacts = self._rows(
            """
            select
                id,
                run_id,
                artifact_type,
                artifact_code,
                artifact_name,
                storage_backend,
                uri,
                mime_type,
                file_size_bytes,
                checksum_sha256,
                artifact_metadata,
                created_at
            from ops_run_artifact
            where run_id = :run_id
            order by id
            """,
            {"run_id": run_id},
        )

        return {
            "module": "M8.1",
            "query": "run",
            "run_id": run_id,
            "run": run,
            "steps": steps,
            "metrics": metrics,
            "series_preview": series,
            "artifacts": artifacts,
            "checks": {
                "run_exists": run is not None,
            },
            "overall_status": "PASS" if run is not None else "FAIL",
        }

    def query_paper_chain(
        self,
        *,
        portfolio_id: int,
        target_run_id: int,
        order_run_id: int | None = None,
        fill_run_id: int | None = None,
        position_run_id: int | None = None,
        snapshot_run_id: int | None = None,
    ) -> dict[str, Any]:
        target = self._target_summary(
            run_id=target_run_id,
            portfolio_id=portfolio_id,
        )

        order = (
            self._order_summary(run_id=order_run_id, portfolio_id=portfolio_id)
            if order_run_id is not None
            else None
        )
        fill = (
            self._fill_summary(run_id=fill_run_id, portfolio_id=portfolio_id)
            if fill_run_id is not None
            else None
        )
        position = (
            self._position_summary(run_id=position_run_id, portfolio_id=portfolio_id)
            if position_run_id is not None
            else None
        )
        snapshot = (
            self._snapshot_summary(run_id=snapshot_run_id, portfolio_id=portfolio_id)
            if snapshot_run_id is not None
            else None
        )

        checks = {
            "target_exists": int((target or {}).get("target_count") or 0) > 0,
            "order_checked": order_run_id is not None,
            "fill_checked": fill_run_id is not None,
            "position_checked": position_run_id is not None,
            "snapshot_checked": snapshot_run_id is not None,
        }

        if order is not None:
            checks["order_exists"] = int(order.get("order_count") or 0) > 0
        if fill is not None:
            checks["fill_exists"] = int(fill.get("fill_count") or 0) > 0
        if position is not None:
            checks["position_exists"] = int(position.get("position_count") or 0) > 0
        if snapshot is not None:
            checks["snapshot_exists"] = int(snapshot.get("snapshot_count") or 0) > 0

        required_checks = [checks.get("target_exists", False)]
        if order_run_id is not None:
            required_checks.append(checks.get("order_exists", False))
        if fill_run_id is not None:
            required_checks.append(checks.get("fill_exists", False))
        if position_run_id is not None:
            required_checks.append(checks.get("position_exists", False))
        if snapshot_run_id is not None:
            required_checks.append(checks.get("snapshot_exists", False))

        return {
            "module": "M8.1",
            "query": "paper_chain",
            "portfolio_id": portfolio_id,
            "runs": {
                "target_run_id": target_run_id,
                "order_run_id": order_run_id,
                "fill_run_id": fill_run_id,
                "position_run_id": position_run_id,
                "snapshot_run_id": snapshot_run_id,
            },
            "target": target,
            "order": order,
            "fill": fill,
            "position": position,
            "snapshot": snapshot,
            "checks": checks,
            "overall_status": "PASS" if all(required_checks) else "FAIL",
        }

    def query_latest_runs(
        self,
        *,
        portfolio_id: int,
        profile_code: str | None = None,
    ) -> dict[str, Any]:
        latest_snapshot = self._one(
            """
            select
                run_id as snapshot_run_id,
                snapshot_date,
                id as snapshot_id,
                holding_count,
                total_equity,
                created_at
            from trading_paper_portfolio_snapshot
            where portfolio_id = cast(:portfolio_id as bigint)
            order by snapshot_date desc, id desc
            limit 1
            """,
            {"portfolio_id": portfolio_id},
        )

        latest_position = None
        latest_fill = None
        latest_order = None
        latest_target = None

        if latest_snapshot is not None:
            latest_position = self._one(
                """
                select
                    run_id as position_run_id,
                    position_date,
                    count(*) as position_count,
                    count(*) filter (where coalesce(quantity, 0) > 0) as open_position_count,
                    coalesce(sum(quantity), 0) as quantity_total,
                    coalesce(sum(market_value), 0) as market_value_total
                from trading_paper_position
                where portfolio_id = cast(:portfolio_id as bigint)
                  and position_date <= cast(:snapshot_date as date)
                group by run_id, position_date
                order by position_date desc, run_id desc
                limit 1
                """,
                {
                    "portfolio_id": portfolio_id,
                    "snapshot_date": latest_snapshot["snapshot_date"],
                },
            )

            latest_fill = self._one(
                """
                select
                    run_id as fill_run_id,
                    fill_date,
                    count(*) as fill_count,
                    coalesce(sum(fill_quantity), 0) as fill_quantity_total,
                    coalesce(sum(gross_amount), 0) as gross_amount_total,
                    coalesce(sum(cash_delta), 0) as cash_delta_total
                from trading_paper_fill
                where portfolio_id = cast(:portfolio_id as bigint)
                  and fill_date <= cast(:snapshot_date as date)
                group by run_id, fill_date
                order by fill_date desc, run_id desc
                limit 1
                """,
                {
                    "portfolio_id": portfolio_id,
                    "snapshot_date": latest_snapshot["snapshot_date"],
                },
            )

        if latest_fill is not None:
            latest_order = self._one(
                """
                select
                    o.run_id as order_run_id,
                    o.effective_date,
                    count(*) as order_count,
                    count(*) filter (where o.order_side = 'BUY') as buy_order_count,
                    count(*) filter (where o.order_side = 'SELL') as sell_order_count,
                    coalesce(sum(o.order_quantity), 0) as order_quantity_total
                from trading_paper_fill f
                join trading_paper_order o
                  on o.id = f.order_id
                where f.portfolio_id = cast(:portfolio_id as bigint)
                  and f.run_id = cast(:fill_run_id as bigint)
                group by o.run_id, o.effective_date
                order by count(*) desc, o.run_id desc
                limit 1
                """,
                {
                    "portfolio_id": portfolio_id,
                    "fill_run_id": latest_fill["fill_run_id"],
                },
            )

        if latest_order is not None:
            latest_target = self._one(
                """
                select
                    t.run_id as target_run_id,
                    t.as_of_date,
                    t.effective_date,
                    count(*) as linked_target_count,
                    coalesce(sum(t.target_quantity), 0) as linked_target_quantity_total,
                    coalesce(sum(t.target_amount), 0) as linked_target_amount_total
                from trading_paper_order o
                join trading_paper_target_position t
                  on t.id = o.target_position_id
                where o.portfolio_id = cast(:portfolio_id as bigint)
                  and o.run_id = cast(:order_run_id as bigint)
                group by t.run_id, t.as_of_date, t.effective_date
                order by count(*) desc, t.run_id desc
                limit 1
                """,
                {
                    "portfolio_id": portfolio_id,
                    "order_run_id": latest_order["order_run_id"],
                },
            )

        latest_risk = self._one(
            """
            select
                rd.run_id as risk_run_id,
                rd.source_target_run_id,
                rd.adjusted_target_run_id,
                rd.portfolio_id,
                rp.profile_code,
                count(*) as decision_count,
                count(*) filter (where rd.decision_type = 'PASS') as pass_count,
                count(*) filter (where rd.decision_type = 'WARN') as warn_count,
                count(*) filter (where rd.decision_type = 'REJECT') as reject_count,
                count(*) filter (where rd.decision_type = 'ADJUST') as adjust_count,
                min(rd.decision_date) as min_decision_date,
                max(rd.decision_date) as max_decision_date,
                max(rd.created_at) as latest_decision_created_at
            from risk_decision rd
            left join risk_profile rp
              on rp.id = rd.risk_profile_id
            where rd.portfolio_id = cast(:portfolio_id as bigint)
              and (
                    cast(:profile_code as text) is null
                    or rp.profile_code = cast(:profile_code as text)
                  )
            group by
                rd.run_id,
                rd.source_target_run_id,
                rd.adjusted_target_run_id,
                rd.portfolio_id,
                rp.profile_code
            order by max(rd.created_at) desc, rd.run_id desc
            limit 1
            """,
            {
                "portfolio_id": portfolio_id,
                "profile_code": profile_code,
            },
        )

        trading_chain = {
            "target_run_id": latest_target["target_run_id"] if latest_target else None,
            "order_run_id": latest_order["order_run_id"] if latest_order else None,
            "fill_run_id": latest_fill["fill_run_id"] if latest_fill else None,
            "position_run_id": latest_position["position_run_id"] if latest_position else None,
            "snapshot_run_id": latest_snapshot["snapshot_run_id"] if latest_snapshot else None,
        }

        risk_chain = {
            "risk_run_id": latest_risk["risk_run_id"] if latest_risk else None,
            "source_target_run_id": latest_risk["source_target_run_id"] if latest_risk else None,
            "adjusted_target_run_id": latest_risk["adjusted_target_run_id"] if latest_risk else None,
        }

        powershell_trading_env = self._powershell_env(
            {
                "M8_PORTFOLIO_ID": portfolio_id,
                "M8_TARGET_RUN_ID": trading_chain["target_run_id"],
                "M8_ORDER_RUN_ID": trading_chain["order_run_id"],
                "M8_FILL_RUN_ID": trading_chain["fill_run_id"],
                "M8_POSITION_RUN_ID": trading_chain["position_run_id"],
                "M8_SNAPSHOT_RUN_ID": trading_chain["snapshot_run_id"],
            }
        )

        powershell_risk_env = self._powershell_env(
            {
                "M8_PORTFOLIO_ID": portfolio_id,
                "M8_SOURCE_TARGET_RUN_ID": risk_chain["source_target_run_id"],
                "M8_ADJUSTED_TARGET_RUN_ID": risk_chain["adjusted_target_run_id"],
                "M8_RISK_RUN_ID": risk_chain["risk_run_id"],
            }
        )

        checks = {
            "latest_snapshot_exists": latest_snapshot is not None,
            "latest_position_exists": latest_position is not None,
            "latest_fill_exists": latest_fill is not None,
            "latest_order_exists": latest_order is not None,
            "latest_target_exists": latest_target is not None,
            "latest_risk_exists": latest_risk is not None,
        }

        return {
            "module": "M8.1",
            "query": "latest_runs",
            "portfolio_id": portfolio_id,
            "profile_code": profile_code,
            "trading_chain": trading_chain,
            "risk_chain": risk_chain,
            "details": {
                "latest_snapshot": latest_snapshot,
                "latest_position": latest_position,
                "latest_fill": latest_fill,
                "latest_order": latest_order,
                "latest_target": latest_target,
                "latest_risk": latest_risk,
            },
            "powershell_env": {
                "trading_chain": powershell_trading_env,
                "risk_chain": powershell_risk_env,
            },
            "next_commands": {
                "query_paper_chain": "python -m stock_quant_v2.scripts.m8_query_paper_chain",
                "query_risk_decision": "python -m stock_quant_v2.scripts.m8_query_risk_decision",
                "query_target_diff": "python -m stock_quant_v2.scripts.m8_query_target_diff",
            },
            "checks": checks,
            "overall_status": "PASS" if all(checks.values()) else "WARN",
        }

    def query_target_diff(
        self,
        *,
        portfolio_id: int,
        source_target_run_id: int,
        adjusted_target_run_id: int,
        risk_run_id: int | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        source = self._target_summary(
            run_id=source_target_run_id,
            portfolio_id=portfolio_id,
        )
        adjusted = self._target_summary(
            run_id=adjusted_target_run_id,
            portfolio_id=portfolio_id,
        )

        decision_summary = self.query_risk_decision(
            portfolio_id=portfolio_id,
            source_target_run_id=source_target_run_id,
            adjusted_target_run_id=adjusted_target_run_id,
            risk_run_id=risk_run_id,
            limit=limit,
        )

        diff_rows = self._rows(
            """
            with mapped as (
                select
                    rd.portfolio_id,
                    rd.source_target_run_id,
                    rd.adjusted_target_run_id,
                    rd.run_id as risk_run_id,
                    rd.instrument_id,
                    rd.source_target_position_id,
                    rd.adjusted_target_position_id,

                    count(*) as decision_count,
                    count(*) filter (where rd.decision_type = 'PASS') as pass_count,
                    count(*) filter (where rd.decision_type = 'WARN') as warn_count,
                    count(*) filter (where rd.decision_type = 'REJECT') as reject_count,
                    count(*) filter (where rd.decision_type = 'ADJUST') as adjust_count,

                    string_agg(distinct rd.decision_type, ',' order by rd.decision_type) as decision_types,
                    string_agg(distinct rd.reason_code, ',' order by rd.reason_code) as reason_codes,
                    string_agg(distinct rd.action_taken, ',' order by rd.action_taken) as actions_taken,

                    max(s.target_side) as source_target_side,
                    max(a.target_side) as adjusted_target_side,

                    max(s.target_weight) as source_target_weight,
                    max(a.target_weight) as adjusted_target_weight,

                    max(s.target_quantity) as source_target_quantity,
                    max(a.target_quantity) as adjusted_target_quantity,

                    max(s.target_amount) as source_target_amount,
                    max(a.target_amount) as adjusted_target_amount,

                    max(s.status) as source_status,
                    max(a.status) as adjusted_status
                from risk_decision rd
                left join trading_paper_target_position s
                  on s.id = rd.source_target_position_id
                left join trading_paper_target_position a
                  on a.id = rd.adjusted_target_position_id
                where rd.portfolio_id = cast(:portfolio_id as bigint)
                  and rd.source_target_run_id = cast(:source_target_run_id as bigint)
                  and rd.adjusted_target_run_id = cast(:adjusted_target_run_id as bigint)
                  and (
                        cast(:risk_run_id as bigint) is null
                        or rd.run_id = cast(:risk_run_id as bigint)
                      )
                group by
                    rd.portfolio_id,
                    rd.source_target_run_id,
                    rd.adjusted_target_run_id,
                    rd.run_id,
                    rd.instrument_id,
                    rd.source_target_position_id,
                    rd.adjusted_target_position_id
            )
            select
                *,
                case
                    when reject_count > 0 then 'REJECT'
                    when adjust_count > 0 then 'ADJUST'
                    when warn_count > 0 then 'WARN'
                    else 'PASS'
                end as final_decision_type,
                coalesce(adjusted_target_weight, 0) - coalesce(source_target_weight, 0) as target_weight_delta,
                coalesce(adjusted_target_quantity, 0) - coalesce(source_target_quantity, 0) as target_quantity_delta,
                coalesce(adjusted_target_amount, 0) - coalesce(source_target_amount, 0) as target_amount_delta
            from mapped
            order by
                case
                    when reject_count > 0 then 1
                    when adjust_count > 0 then 2
                    when warn_count > 0 then 3
                    else 4
                end,
                instrument_id
            limit cast(:limit as bigint)
            """,
            {
                "portfolio_id": portfolio_id,
                "source_target_run_id": source_target_run_id,
                "adjusted_target_run_id": adjusted_target_run_id,
                "risk_run_id": risk_run_id,
                "limit": limit,
            },
        )

        source_quantity = self._decimal_or_zero((source or {}).get("target_quantity_total"))
        adjusted_quantity = self._decimal_or_zero((adjusted or {}).get("target_quantity_total"))
        source_amount = self._decimal_or_zero((source or {}).get("target_amount_total"))
        adjusted_amount = self._decimal_or_zero((adjusted or {}).get("target_amount_total"))
        source_weight = self._decimal_or_zero((source or {}).get("target_weight_total"))
        adjusted_weight = self._decimal_or_zero((adjusted or {}).get("target_weight_total"))

        checks = {
            "source_target_exists": int((source or {}).get("target_count") or 0) > 0,
            "adjusted_target_exists": int((adjusted or {}).get("target_count") or 0) > 0,
            "risk_decision_exists": int(((decision_summary.get("summary") or {}).get("decision_count")) or 0) > 0,
        }

        return {
            "module": "M8.1",
            "query": "target_diff",
            "portfolio_id": portfolio_id,
            "source_target_run_id": source_target_run_id,
            "adjusted_target_run_id": adjusted_target_run_id,
            "risk_run_id": risk_run_id,
            "source": source,
            "adjusted": adjusted,
            "diff_summary": {
                "target_weight_delta": adjusted_weight - source_weight,
                "target_quantity_delta": adjusted_quantity - source_quantity,
                "target_amount_delta": adjusted_amount - source_amount,
            },
            "risk_summary": decision_summary.get("summary"),
            "reason_summary": decision_summary.get("reason_summary"),
            "diff_rows_preview": diff_rows,
            "limit": limit,
            "checks": checks,
            "overall_status": "PASS" if all(checks.values()) else "FAIL",
        }

    def query_portfolio_snapshot(
        self,
        *,
        portfolio_id: int,
        snapshot_run_id: int | None = None,
        snapshot_date: date | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "portfolio_id": portfolio_id,
            "snapshot_run_id": snapshot_run_id,
            "snapshot_date": snapshot_date,
        }

        snapshot = self._one(
            """
            select
                id,
                run_id,
                portfolio_id,
                snapshot_date,
                cash_balance,
                market_value,
                total_equity,
                gross_exposure,
                net_exposure,
                holding_count,
                daily_pnl,
                cumulative_pnl,
                daily_return,
                cumulative_return,
                turnover_amount,
                turnover_rate,
                created_at,
                updated_at
            from trading_paper_portfolio_snapshot
            where portfolio_id = cast(:portfolio_id as bigint)
              and (
                    cast(:snapshot_run_id as bigint) is null
                    or run_id = cast(:snapshot_run_id as bigint)
                  )
              and (
                    cast(:snapshot_date as date) is null
                    or snapshot_date = cast(:snapshot_date as date)
                  )
            order by snapshot_date desc, id desc
            limit 1
            """,
            params,
        )

        return {
            "module": "M8.1",
            "query": "portfolio_snapshot",
            "portfolio_id": portfolio_id,
            "snapshot_run_id": snapshot_run_id,
            "snapshot_date": snapshot_date,
            "snapshot": snapshot,
            "checks": {
                "snapshot_exists": snapshot is not None,
            },
            "overall_status": "PASS" if snapshot is not None else "FAIL",
        }

    def query_risk_profile(
        self,
        *,
        profile_code: str | None = None,
    ) -> dict[str, Any]:
        profiles = self._rows(
            """
            select
                id,
                profile_code,
                profile_name,
                profile_type,
                market_code,
                enabled,
                description,
                created_at,
                updated_at
            from risk_profile
            where (
                cast(:profile_code as text) is null
                or profile_code = cast(:profile_code as text)
            )
            order by id
            """,
            {"profile_code": profile_code},
        )

        rules = self._rows(
            """
            select
                rp.profile_code,
                rp.profile_name,
                rpr.priority,
                rpr.action,
                rpr.enabled as profile_rule_enabled,
                rpr.params_json,
                rr.rule_code,
                rr.rule_name,
                rr.rule_type,
                rr.default_action,
                rr.default_params_json,
                rr.enabled as rule_enabled
            from risk_profile rp
            join risk_profile_rule rpr
              on rpr.profile_id = rp.id
            join risk_rule rr
              on rr.id = rpr.rule_id
            where (
                cast(:profile_code as text) is null
                or rp.profile_code = cast(:profile_code as text)
            )
            order by rp.profile_code, rpr.priority, rr.rule_code
            """,
            {"profile_code": profile_code},
        )

        return {
            "module": "M8.1",
            "query": "risk_profile",
            "profile_code": profile_code,
            "profile_count": len(profiles),
            "profiles": profiles,
            "rules": rules,
            "checks": {
                "profile_exists": len(profiles) > 0,
            },
            "overall_status": "PASS" if len(profiles) > 0 else "FAIL",
        }

    def query_risk_decision(
        self,
        *,
        portfolio_id: int,
        source_target_run_id: int | None = None,
        adjusted_target_run_id: int | None = None,
        risk_run_id: int | None = None,
        limit: int = 200,
        profile_code: str | None = None,
    ) -> dict[str, Any]:
        from_sql, where_sql, params = self._build_risk_decision_query_parts(
            portfolio_id=portfolio_id,
            source_target_run_id=source_target_run_id,
            adjusted_target_run_id=adjusted_target_run_id,
            risk_run_id=risk_run_id,
            profile_code=profile_code,
        )

        summary = self._one(
            f"""
            select
                count(*) as decision_count,
                count(*) filter (where rd.decision_type = 'PASS') as pass_count,
                count(*) filter (where rd.decision_type = 'WARN') as warn_count,
                count(*) filter (where rd.decision_type = 'REJECT') as reject_count,
                count(*) filter (where rd.decision_type = 'ADJUST') as adjust_count,
                min(rd.decision_date) as min_decision_date,
                max(rd.decision_date) as max_decision_date
            {from_sql}
            where {where_sql}
            """,
            params,
        )

        reason_summary = self._rows(
            f"""
            select
                rd.decision_type,
                rd.reason_code,
                count(*) as cnt
            {from_sql}
            where {where_sql}
            group by rd.decision_type, rd.reason_code
            order by rd.decision_type, rd.reason_code
            """,
            params,
        )

        decision_params = dict(params)
        decision_params["limit"] = int(limit)

        decisions = self._rows(
            f"""
            select
                rd.id,
                rd.run_id,
                rd.portfolio_id,
                rd.source_target_run_id,
                rd.adjusted_target_run_id,
                rp.profile_code,
                rr.rule_code,
                rd.source_target_position_id,
                rd.adjusted_target_position_id,
                rd.instrument_id,
                rd.decision_date,
                rd.decision_type,
                rd.reason_code,
                rd.action_taken,
                rd.before_target_weight,
                rd.after_target_weight,
                rd.before_target_quantity,
                rd.after_target_quantity,
                rd.before_target_amount,
                rd.after_target_amount,
                rd.message,
                rd.payload_json,
                rd.created_at
            {from_sql}
            where {where_sql}
            order by rd.id
            limit cast(:limit as bigint)
            """,
            decision_params,
        )

        decision_count = int((summary or {}).get("decision_count") or 0)

        return {
            "module": "M8.1",
            "query": "risk_decision",
            "portfolio_id": portfolio_id,
            "profile_code": profile_code,
            "source_target_run_id": source_target_run_id,
            "adjusted_target_run_id": adjusted_target_run_id,
            "risk_run_id": risk_run_id,
            "summary": summary,
            "reason_summary": reason_summary,
            "decisions_preview": decisions,
            "decisions": decisions,
            "limit": limit,
            "checks": {
                "decision_exists": decision_count > 0,
            },
            "overall_status": "PASS" if decision_count > 0 else "FAIL",
        }

    def export_risk_report(
        self,
        *,
        output_dir: Path,
        portfolio_id: int,
        source_target_run_id: int,
        adjusted_target_run_id: int,
        risk_run_id: int | None = None,
        profile_code: str | None = None,
    ) -> dict[str, Any]:
        output_dir.mkdir(parents=True, exist_ok=True)

        payload = self.query_risk_decision(
            portfolio_id=portfolio_id,
            source_target_run_id=source_target_run_id,
            adjusted_target_run_id=adjusted_target_run_id,
            risk_run_id=risk_run_id,
            limit=100000,
            profile_code=profile_code,
        )

        source_target = self._target_summary(
            run_id=source_target_run_id,
            portfolio_id=portfolio_id,
        )
        adjusted_target = self._target_summary(
            run_id=adjusted_target_run_id,
            portfolio_id=portfolio_id,
        )

        report = {
            **payload,
            "source_target": source_target,
            "adjusted_target": adjusted_target,
            "exported_at": datetime.utcnow().isoformat(),
        }

        stem = f"m8_risk_report_p{portfolio_id}_src{source_target_run_id}_adj{adjusted_target_run_id}"

        json_path = output_dir / f"{stem}.json"
        csv_path = output_dir / f"{stem}_decisions.csv"
        md_path = output_dir / f"{stem}.md"

        json_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=self._json_default),
            encoding="utf-8",
        )

        self._write_decision_csv(csv_path, report["decisions_preview"])
        md_path.write_text(
            self._render_risk_report_md(
                portfolio_id=portfolio_id,
                source_target_run_id=source_target_run_id,
                adjusted_target_run_id=adjusted_target_run_id,
                risk_run_id=risk_run_id,
                report=report,
            ),
            encoding="utf-8",
        )

        return {
            "module": "M8.1",
            "query": "export_risk_report",
            "portfolio_id": portfolio_id,
            "source_target_run_id": source_target_run_id,
            "adjusted_target_run_id": adjusted_target_run_id,
            "risk_run_id": risk_run_id,
            "files": {
                "json": str(json_path),
                "csv": str(csv_path),
                "markdown": str(md_path),
            },
            "summary": payload["summary"],
            "overall_status": payload["overall_status"],
        }

    # =========================
    # Private summary helpers
    # =========================

    def _target_summary(self, *, run_id: int, portfolio_id: int) -> dict[str, Any]:
        return self._one(
            """
            select
                count(*) as target_count,
                count(*) filter (where status = 'REJECTED') as rejected_target_count,
                count(*) filter (where status like 'RISK%') as risk_status_count,
                min(as_of_date) as min_as_of_date,
                max(as_of_date) as max_as_of_date,
                min(effective_date) as min_effective_date,
                max(effective_date) as max_effective_date,
                coalesce(sum(target_weight), 0) as target_weight_total,
                coalesce(sum(target_quantity), 0) as target_quantity_total,
                coalesce(sum(target_amount), 0) as target_amount_total
            from trading_paper_target_position
            where run_id = :run_id
              and portfolio_id = :portfolio_id
            """,
            {"run_id": run_id, "portfolio_id": portfolio_id},
        )

    def _order_summary(self, *, run_id: int, portfolio_id: int) -> dict[str, Any]:
        return self._one(
            """
            select
                count(*) as order_count,
                count(*) filter (where order_side = 'BUY') as buy_order_count,
                count(*) filter (where order_side = 'SELL') as sell_order_count,
                min(order_date) as min_order_date,
                max(order_date) as max_order_date,
                min(effective_date) as min_effective_date,
                max(effective_date) as max_effective_date,
                coalesce(sum(order_quantity), 0) as order_quantity_total,
                coalesce(sum(estimated_gross_amount), 0) as estimated_gross_amount_total,
                coalesce(sum(estimated_fee), 0) as estimated_fee_total,
                coalesce(sum(estimated_net_amount), 0) as estimated_net_amount_total
            from trading_paper_order
            where run_id = :run_id
              and portfolio_id = :portfolio_id
            """,
            {"run_id": run_id, "portfolio_id": portfolio_id},
        )

    def _fill_summary(self, *, run_id: int, portfolio_id: int) -> dict[str, Any]:
        return self._one(
            """
            select
                count(*) as fill_count,
                min(fill_date) as min_fill_date,
                max(fill_date) as max_fill_date,
                coalesce(sum(fill_quantity), 0) as fill_quantity_total,
                coalesce(sum(gross_amount), 0) as gross_amount_total,
                coalesce(sum(total_fee_amount), 0) as total_fee_amount_total,
                coalesce(sum(net_amount), 0) as net_amount_total,
                coalesce(sum(cash_delta), 0) as cash_delta_total,
                coalesce(sum(slippage_amount), 0) as slippage_amount_total
            from trading_paper_fill
            where run_id = :run_id
              and portfolio_id = :portfolio_id
            """,
            {"run_id": run_id, "portfolio_id": portfolio_id},
        )

    def _position_summary(self, *, run_id: int, portfolio_id: int) -> dict[str, Any]:
        return self._one(
            """
            select
                count(*) as position_count,
                count(*) filter (where coalesce(quantity, 0) > 0) as open_position_count,
                count(*) filter (where coalesce(quantity, 0) = 0) as closed_position_count,
                min(position_date) as min_position_date,
                max(position_date) as max_position_date,
                coalesce(sum(quantity), 0) as quantity_total,
                coalesce(sum(available_quantity), 0) as available_quantity_total,
                coalesce(sum(cost_amount), 0) as cost_amount_total,
                coalesce(sum(market_value), 0) as market_value_total,
                coalesce(sum(unrealized_pnl), 0) as unrealized_pnl_total,
                coalesce(sum(realized_pnl), 0) as realized_pnl_total,
                coalesce(sum(total_pnl), 0) as total_pnl_total
            from trading_paper_position
            where run_id = :run_id
              and portfolio_id = :portfolio_id
            """,
            {"run_id": run_id, "portfolio_id": portfolio_id},
        )

    def _snapshot_summary(self, *, run_id: int, portfolio_id: int) -> dict[str, Any]:
        return self._one(
            """
            select
                count(*) as snapshot_count,
                min(snapshot_date) as min_snapshot_date,
                max(snapshot_date) as max_snapshot_date,
                coalesce(sum(cash_balance), 0) as cash_balance_total,
                coalesce(sum(market_value), 0) as market_value_total,
                coalesce(sum(total_equity), 0) as total_equity_total,
                coalesce(sum(gross_exposure), 0) as gross_exposure_total,
                coalesce(sum(net_exposure), 0) as net_exposure_total,
                max(holding_count) as holding_count,
                coalesce(sum(daily_pnl), 0) as daily_pnl_total,
                coalesce(sum(cumulative_pnl), 0) as cumulative_pnl_total
            from trading_paper_portfolio_snapshot
            where run_id = :run_id
              and portfolio_id = :portfolio_id
            """,
            {"run_id": run_id, "portfolio_id": portfolio_id},
        )

    # =========================
    # Low-level DB helpers
    # =========================

    def _rows(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        rows = self.session.execute(text(sql), params).mappings().all()
        return [dict(row) for row in rows]

    def _one(self, sql: str, params: dict[str, Any]) -> dict[str, Any] | None:
        row = self.session.execute(text(sql), params).mappings().one_or_none()
        return dict(row) if row is not None else None

    # =========================
    # Serialization / filesystem helpers
    # =========================

    @staticmethod
    def _json_default(value: Any) -> Any:
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        return str(value)

    @staticmethod
    def _decimal_or_zero(value: Any) -> Decimal:
        if value is None:
            return Decimal("0")
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    @staticmethod
    def _powershell_env(values: dict[str, Any]) -> list[str]:
        lines: list[str] = []
        for key, value in values.items():
            if value is None:
                continue
            lines.append(f'$env:{key}="{value}"')
        return lines

    def _write_decision_csv(self, path: Path, rows: list[dict[str, Any]]) -> None:
        fields = [
            "id",
            "run_id",
            "portfolio_id",
            "source_target_run_id",
            "adjusted_target_run_id",
            "profile_code",
            "rule_code",
            "instrument_id",
            "decision_date",
            "decision_type",
            "reason_code",
            "action_taken",
            "before_target_weight",
            "after_target_weight",
            "before_target_quantity",
            "after_target_quantity",
            "before_target_amount",
            "after_target_amount",
            "message",
        ]

        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    key: self._json_default(value)
                    for key, value in row.items()
                })

    def _render_risk_report_md(
        self,
        *,
        portfolio_id: int,
        source_target_run_id: int,
        adjusted_target_run_id: int,
        risk_run_id: int | None,
        report: dict[str, Any],
    ) -> str:
        summary = report.get("summary") or {}
        source = report.get("source_target") or {}
        adjusted = report.get("adjusted_target") or {}
        reasons = report.get("reason_summary") or []

        lines = [
            "# M8.1 Risk Report",
            "",
            f"- portfolio_id: `{portfolio_id}`",
            f"- risk_run_id: `{risk_run_id}`",
            f"- source_target_run_id: `{source_target_run_id}`",
            f"- adjusted_target_run_id: `{adjusted_target_run_id}`",
            "",
            "## Summary",
            "",
            f"- decision_count: `{summary.get('decision_count')}`",
            f"- pass_count: `{summary.get('pass_count')}`",
            f"- warn_count: `{summary.get('warn_count')}`",
            f"- reject_count: `{summary.get('reject_count')}`",
            f"- adjust_count: `{summary.get('adjust_count')}`",
            f"- min_decision_date: `{summary.get('min_decision_date')}`",
            f"- max_decision_date: `{summary.get('max_decision_date')}`",
            "",
            "## Target Diff",
            "",
            f"- source_target_count: `{source.get('target_count')}`",
            f"- adjusted_target_count: `{adjusted.get('target_count')}`",
            f"- source_target_quantity_total: `{source.get('target_quantity_total')}`",
            f"- adjusted_target_quantity_total: `{adjusted.get('target_quantity_total')}`",
            f"- source_target_amount_total: `{source.get('target_amount_total')}`",
            f"- adjusted_target_amount_total: `{adjusted.get('target_amount_total')}`",
            "",
            "## Reason Summary",
            "",
            "| decision_type | reason_code | count |",
            "|---|---|---:|",
        ]

        for row in reasons:
            lines.append(
                f"| {row.get('decision_type')} | {row.get('reason_code')} | {row.get('cnt')} |"
            )

        lines.append("")
        return "\n".join(lines)

    def _json_safe(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {k: self._json_safe(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._json_safe(v) for v in value]
        if isinstance(value, tuple):
            return [self._json_safe(v) for v in value]
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        return value

    def _project_root(self) -> Path:
        return Path(__file__).resolve().parents[4]

    def _ensure_dir(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

    def _write_json_file(self, path: Path, payload: dict) -> None:
        self._ensure_dir(path.parent)
        path.write_text(
            json.dumps(self._json_safe(payload), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _write_markdown_file(self, path: Path, content: str) -> None:
        self._ensure_dir(path.parent)
        path.write_text(content, encoding="utf-8")

    def _write_csv_file(self, path: Path, rows: list[dict]) -> None:
        self._ensure_dir(path.parent)
        if not rows:
            with path.open("w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["empty"])
            return

        fieldnames: list[str] = []
        for row in rows:
            for key in row.keys():
                if key not in fieldnames:
                    fieldnames.append(key)

        with path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: self._json_safe(v) for k, v in row.items()})

    # =========================
    # Risk-decision query helpers
    # =========================

    def _build_risk_decision_query_parts(
        self,
        *,
        portfolio_id: int,
        source_target_run_id: int | None = None,
        adjusted_target_run_id: int | None = None,
        risk_run_id: int | None = None,
        profile_code: str | None = None,
    ) -> tuple[str, str, dict[str, Any]]:
        """
        关键修复：
        不使用
            (:risk_run_id is null or run_id = :risk_run_id)
        这种写法，避免 PostgreSQL/psycopg 对 None 参数类型歧义。
        """
        from_sql = """
        from risk_decision rd
        left join risk_profile rp
          on rp.id = rd.risk_profile_id
        left join risk_rule rr
          on rr.id = rd.risk_rule_id
        """

        where_parts = ["rd.portfolio_id = :portfolio_id"]
        params: dict[str, Any] = {"portfolio_id": portfolio_id}

        if source_target_run_id is not None:
            where_parts.append("rd.source_target_run_id = :source_target_run_id")
            params["source_target_run_id"] = source_target_run_id

        if adjusted_target_run_id is not None:
            where_parts.append("rd.adjusted_target_run_id = :adjusted_target_run_id")
            params["adjusted_target_run_id"] = adjusted_target_run_id

        if risk_run_id is not None:
            where_parts.append("rd.run_id = :risk_run_id")
            params["risk_run_id"] = risk_run_id

        if profile_code is not None:
            where_parts.append("rp.profile_code = :profile_code")
            params["profile_code"] = profile_code

        return from_sql, " and ".join(where_parts), params
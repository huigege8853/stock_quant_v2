from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from stock_quant_v2.ops_domain.services.m8_query_service import M8QueryService


class M8OpsHygieneService:
    def __init__(self, session: Session):
        self.session = session
        self.query_service = M8QueryService(session)

    def ops_run_hygiene_check(
        self,
        *,
        portfolio_id: int,
        profile_code: str | None = None,
        stale_after_hours: int = 12,
        limit: int = 200,
        include_protected: bool = False,
    ) -> dict[str, Any]:
        latest = self.query_service.query_latest_runs(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
        )

        status_counts = self._rows(
            """
            select
                status,
                count(*) as cnt
            from ops_run
            group by status
            order by status
            """,
            {},
        )

        stale = self.query_stale_runs(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
            stale_after_hours=stale_after_hours,
            limit=limit,
            include_protected=include_protected,
        )

        running_count = sum(
            int(row["cnt"] or 0)
            for row in status_counts
            if row.get("status") == "RUNNING"
        )

        stale_candidate_count = len(stale["candidates"])
        protected_running_count = len(stale["protected_running_runs"])

        checks = {
            "latest_runs_pass": {
                "status": "PASS" if latest.get("overall_status") == "PASS" else "FAIL",
                "message": "latest trading/risk chain should be identifiable",
            },
            "stale_query_pass": {
                "status": "PASS",
                "message": "stale RUNNING run query executed",
            },
        }

        warnings: list[dict[str, Any]] = []

        if running_count > 0:
            warnings.append(
                {
                    "warning_code": "RUNNING_RUNS_EXIST",
                    "message": f"ops_run 中仍有 RUNNING：{running_count}",
                }
            )

        if stale_candidate_count > 0:
            warnings.append(
                {
                    "warning_code": "STALE_RUN_CANDIDATES_EXIST",
                    "message": f"发现可治理 stale candidates：{stale_candidate_count}",
                }
            )

        if protected_running_count > 0:
            warnings.append(
                {
                    "warning_code": "PROTECTED_RUNNING_RUNS_EXIST",
                    "message": (
                        "latest trading/risk chain 中存在 RUNNING run，默认保护不处理："
                        f"{protected_running_count}"
                    ),
                }
            )

        failures = [
            {"check_code": code, "message": item["message"]}
            for code, item in checks.items()
            if item["status"] == "FAIL"
        ]

        if failures:
            overall_status = "FAIL"
        elif warnings:
            overall_status = "WARN"
        else:
            overall_status = "PASS"

        return {
            "module": "M8.4",
            "query": "ops_run_hygiene_check",
            "portfolio_id": portfolio_id,
            "profile_code": profile_code,
            "stale_after_hours": stale_after_hours,
            "include_protected": include_protected,
            "checked_at": datetime.utcnow().isoformat(),
            "latest_runs": latest,
            "status_counts": status_counts,
            "stale_summary": stale["summary"],
            "checks": checks,
            "warnings": warnings,
            "failures": failures,
            "overall_status": overall_status,
        }

    def query_stale_runs(
        self,
        *,
        portfolio_id: int,
        profile_code: str | None = None,
        stale_after_hours: int = 12,
        limit: int = 200,
        include_protected: bool = False,
        run_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        protected_map = self._protected_run_map(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
        )

        rows = self._raw_running_runs(
            stale_after_hours=stale_after_hours,
            limit=limit,
            run_ids=run_ids,
        )

        enriched_rows: list[dict[str, Any]] = []
        candidates: list[dict[str, Any]] = []
        protected_running_runs: list[dict[str, Any]] = []

        for row in rows:
            item = dict(row)
            run_id = int(item["id"])

            output_count = self._output_count(item)
            item["output_count"] = output_count
            item["protected"] = run_id in protected_map
            item["protected_roles"] = protected_map.get(run_id, [])

            if output_count > 0:
                item["recommended_status"] = "SUCCESS"
                item["reason_code"] = "RUNNING_WITH_OUTPUT_ROWS"
                item["reason_message"] = "run 仍为 RUNNING，但已经有业务输出行，建议复核后标记 SUCCESS"
            else:
                item["recommended_status"] = "STALE"
                item["reason_code"] = "RUNNING_WITHOUT_OUTPUT_ROWS"
                item["reason_message"] = "run 长时间 RUNNING 且无业务输出行，建议复核后标记 STALE 或 FAILED"

            if item["protected"] and not include_protected:
                item["candidate_status"] = "PROTECTED"
                item["candidate_message"] = "latest chain run，默认保护，不纳入治理候选"
                protected_running_runs.append(item)
            else:
                item["candidate_status"] = "CANDIDATE"
                item["candidate_message"] = "可进入 dry-run / apply 计划"
                candidates.append(item)

            enriched_rows.append(item)

        return {
            "module": "M8.4",
            "query": "query_stale_runs",
            "portfolio_id": portfolio_id,
            "profile_code": profile_code,
            "stale_after_hours": stale_after_hours,
            "include_protected": include_protected,
            "run_ids": run_ids,
            "summary": {
                "running_rows_scanned": len(rows),
                "candidate_count": len(candidates),
                "protected_running_count": len(protected_running_runs),
                "running_with_output_count": len(
                    [x for x in enriched_rows if x["output_count"] > 0]
                ),
                "running_without_output_count": len(
                    [x for x in enriched_rows if x["output_count"] == 0]
                ),
            },
            "candidates": candidates,
            "protected_running_runs": protected_running_runs,
            "all_rows": enriched_rows,
            "overall_status": "WARN" if candidates or protected_running_runs else "PASS",
        }

    def mark_stale_runs_dry_run(
        self,
        *,
        portfolio_id: int,
        profile_code: str | None = None,
        stale_after_hours: int = 12,
        limit: int = 200,
        include_protected: bool = False,
        target_status: str = "RECOMMENDED",
        run_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        stale = self.query_stale_runs(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
            stale_after_hours=stale_after_hours,
            limit=limit,
            include_protected=include_protected,
            run_ids=run_ids,
        )

        update_plan: list[dict[str, Any]] = []

        for item in stale["candidates"]:
            new_status = (
                item["recommended_status"]
                if target_status == "RECOMMENDED"
                else target_status
            )

            update_plan.append(
                {
                    "run_id": item["id"],
                    "run_type": item.get("run_type"),
                    "run_name": item.get("run_name"),
                    "old_status": item.get("status"),
                    "new_status": new_status,
                    "recommended_status": item.get("recommended_status"),
                    "reason_code": item.get("reason_code"),
                    "reason_message": item.get("reason_message"),
                    "output_count": item.get("output_count"),
                    "age_hours": item.get("age_hours"),
                    "target_rows": item.get("target_rows"),
                    "order_rows": item.get("order_rows"),
                    "fill_rows": item.get("fill_rows"),
                    "position_rows": item.get("position_rows"),
                    "snapshot_rows": item.get("snapshot_rows"),
                    "risk_decision_rows": item.get("risk_decision_rows"),
                }
            )

        return {
            "module": "M8.4",
            "query": "mark_stale_runs_dry_run",
            "portfolio_id": portfolio_id,
            "profile_code": profile_code,
            "stale_after_hours": stale_after_hours,
            "include_protected": include_protected,
            "target_status": target_status,
            "run_ids": run_ids,
            "update_count": len(update_plan),
            "update_plan": update_plan,
            "protected_running_runs": stale["protected_running_runs"],
            "summary": stale["summary"],
            "overall_status": "WARN" if update_plan else "PASS",
        }

    def mark_stale_runs_apply(
        self,
        *,
        portfolio_id: int,
        profile_code: str | None = None,
        stale_after_hours: int = 12,
        limit: int = 200,
        include_protected: bool = False,
        target_status: str = "RECOMMENDED",
        run_ids: list[int] | None = None,
        apply_confirm: bool = False,
    ) -> dict[str, Any]:
        if not apply_confirm:
            raise RuntimeError(
                'M8.4 apply blocked: set M8_APPLY_CONFIRM="YES" to apply updates'
            )

        dry_run = self.mark_stale_runs_dry_run(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
            stale_after_hours=stale_after_hours,
            limit=limit,
            include_protected=include_protected,
            target_status=target_status,
            run_ids=run_ids,
        )

        applied: list[dict[str, Any]] = []

        for item in dry_run["update_plan"]:
            run_id = int(item["run_id"])
            new_status = str(item["new_status"])

            self._update_run_status(
                run_id=run_id,
                new_status=new_status,
                reason_code=str(item.get("reason_code") or ""),
                reason_message=str(item.get("reason_message") or ""),
            )

            applied.append(item)

        self.session.flush()

        return {
            "module": "M8.4",
            "query": "mark_stale_runs_apply",
            "portfolio_id": portfolio_id,
            "profile_code": profile_code,
            "stale_after_hours": stale_after_hours,
            "include_protected": include_protected,
            "target_status": target_status,
            "run_ids": run_ids,
            "applied_count": len(applied),
            "applied": applied,
            "overall_status": "PASS",
        }

    def _raw_running_runs(
        self,
        *,
        stale_after_hours: int,
        limit: int,
        run_ids: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        run_ids_csv = ",".join(str(x) for x in run_ids) if run_ids else None

        return self._rows(
            """
            select
                r.id,
                r.run_type,
                r.run_name,
                r.status,
                r.trigger_type,
                r.requested_at,
                r.started_at,
                r.ended_at,
                r.created_at,
                r.updated_at,
                r.error_message,
                extract(
                    epoch from (
                        now() - coalesce(r.started_at, r.created_at, r.requested_at, now())
                    )
                ) / 3600.0 as age_hours,

                coalesce(t.target_rows, 0) as target_rows,
                coalesce(o.order_rows, 0) as order_rows,
                coalesce(f.fill_rows, 0) as fill_rows,
                coalesce(pos.position_rows, 0) as position_rows,
                coalesce(s.snapshot_rows, 0) as snapshot_rows,
                coalesce(rd.risk_decision_rows, 0) as risk_decision_rows

            from ops_run r

            left join lateral (
                select count(*) as target_rows
                from trading_paper_target_position x
                where x.run_id = r.id
            ) t on true

            left join lateral (
                select count(*) as order_rows
                from trading_paper_order x
                where x.run_id = r.id
            ) o on true

            left join lateral (
                select count(*) as fill_rows
                from trading_paper_fill x
                where x.run_id = r.id
            ) f on true

            left join lateral (
                select count(*) as position_rows
                from trading_paper_position x
                where x.run_id = r.id
            ) pos on true

            left join lateral (
                select count(*) as snapshot_rows
                from trading_paper_portfolio_snapshot x
                where x.run_id = r.id
            ) s on true

            left join lateral (
                select count(*) as risk_decision_rows
                from risk_decision x
                where x.run_id = r.id
            ) rd on true

            where r.status = 'RUNNING'
              and coalesce(r.started_at, r.created_at, r.requested_at, now())
                    <= now() - cast(:stale_after_hours as numeric) * interval '1 hour'
              and (
                    cast(:run_ids_csv as text) is null
                    or r.id in (
                        select cast(value as bigint)
                        from regexp_split_to_table(cast(:run_ids_csv as text), ',') as value
                    )
                  )
            order by coalesce(r.started_at, r.created_at, r.requested_at) asc, r.id asc
            limit cast(:limit as bigint)
            """,
            {
                "stale_after_hours": stale_after_hours,
                "limit": limit,
                "run_ids_csv": run_ids_csv,
            },
        )

    def _protected_run_map(
        self,
        *,
        portfolio_id: int,
        profile_code: str | None,
    ) -> dict[int, list[str]]:
        latest = self.query_service.query_latest_runs(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
        )

        protected: dict[int, list[str]] = {}

        trading_chain = latest.get("trading_chain") or {}
        risk_chain = latest.get("risk_chain") or {}

        for role, run_id in trading_chain.items():
            if run_id is None:
                continue
            protected.setdefault(int(run_id), []).append(role)

        for role, run_id in risk_chain.items():
            if run_id is None:
                continue
            protected.setdefault(int(run_id), []).append(role)

        return protected

    @staticmethod
    def _output_count(row: dict[str, Any]) -> int:
        return (
            int(row.get("target_rows") or 0)
            + int(row.get("order_rows") or 0)
            + int(row.get("fill_rows") or 0)
            + int(row.get("position_rows") or 0)
            + int(row.get("snapshot_rows") or 0)
            + int(row.get("risk_decision_rows") or 0)
        )

    def _update_run_status(
        self,
        *,
        run_id: int,
        new_status: str,
        reason_code: str,
        reason_message: str,
    ) -> None:
        columns = self._ops_run_columns()

        assignments: list[str] = []
        params: dict[str, Any] = {
            "run_id": run_id,
            "new_status": new_status,
            "error_message": (
                f"M8.4 ops hygiene cleanup: {reason_code}; {reason_message}"
            )[:1000],
        }

        if "status" in columns:
            assignments.append("status = :new_status")

        if "ended_at" in columns:
            assignments.append("ended_at = coalesce(ended_at, now())")
        elif "end_time" in columns:
            assignments.append("end_time = coalesce(end_time, now())")
        elif "completed_at" in columns:
            assignments.append("completed_at = coalesce(completed_at, now())")

        if "updated_at" in columns:
            assignments.append("updated_at = now()")

        if "error_message" in columns and new_status in {"FAILED", "STALE"}:
            assignments.append(
                "error_message = coalesce(nullif(error_message, ''), :error_message)"
            )

        if not assignments:
            raise RuntimeError("ops_run has no compatible status/update columns")

        self.session.execute(
            text(
                f"""
                update ops_run
                set {", ".join(assignments)}
                where id = :run_id
                  and status = 'RUNNING'
                """
            ),
            params,
        )

    def _ops_run_columns(self) -> set[str]:
        rows = self.session.execute(
            text(
                """
                select column_name
                from information_schema.columns
                where table_schema = 'public'
                  and table_name = 'ops_run'
                """
            )
        ).all()

        return {row[0] for row in rows}

    def _rows(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        rows = self.session.execute(text(sql), params).mappings().all()
        return [dict(row) for row in rows]
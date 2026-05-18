from __future__ import annotations

import csv
import json
import os
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class WaterlineSpec:
    table_name: str
    date_column: str
    run_id_column: str | None = None
    critical: bool = False
    freshness_basis: str = "report_date"


class ProductionDailyObservationReportBuilder:
    """Build the production-side DailyRun observation report.

    This builder is intentionally production-scoped. It reads production DB state,
    active production paper-campaign config, and existing M6.5/M8 artifacts, then
    writes a total observation report under artifacts/production/daily_observation.
    It does not reuse the research portfolio daily report builder because that
    would blur research and production report semantics.
    """


    GENERIC_THEME_TAG_NAMES: frozenset[str] = frozenset({
        "融资融券",
        "沪股通",
        "深股通",
        "昨日高振幅",
        "昨日涨停",
        "近期新高",
        "近期新低",
        "百日新高",
        "百日新低",
        "昨日连板",
        "昨日首板",
        "昨日炸板",
        "昨日涨停表现",
        "ST板块",
        "破净股",
        "富时罗素",
        "MSCI概念",
        "标普道琼斯A股",
        "参股新三板",
    })
    GENERIC_THEME_TAG_KEYWORDS: tuple[str, ...] = (
        "昨日",
        "近期",
        "百日",
        "融资融券",
        "沪股通",
        "深股通",
        "ST板块",
        "破净",
        "富时罗素",
        "MSCI",
        "标普",
    )

    WATERLINE_SPECS: tuple[WaterlineSpec, ...] = (
        WaterlineSpec("meta_trading_calendar", "trade_date", critical=True),
        WaterlineSpec("core_daily_bar", "trade_date", critical=True),
        WaterlineSpec("core_adjust_factor", "trade_date", critical=True),
        WaterlineSpec("core_price_limit_daily", "trade_date", freshness_basis="signal_as_of_date"),
        WaterlineSpec("market_index_bar", "trade_date", freshness_basis="signal_as_of_date"),
        WaterlineSpec("analytics_feature_snapshot", "trade_date", freshness_basis="signal_as_of_date"),
        WaterlineSpec("analytics_instrument_factor_snapshot", "trade_date", freshness_basis="signal_as_of_date"),
        WaterlineSpec("analytics_instrument_indicator_snapshot", "trade_date", freshness_basis="signal_as_of_date"),
        WaterlineSpec("strategy_signal", "as_of_date", "run_id", critical=True, freshness_basis="signal_as_of_date"),
        WaterlineSpec("trading_paper_target_position", "effective_date", "run_id"),
        WaterlineSpec("trading_paper_order", "effective_date", "run_id"),
        WaterlineSpec("trading_paper_fill", "fill_date", "run_id"),
        WaterlineSpec("trading_paper_position", "position_date", "run_id"),
        WaterlineSpec("trading_paper_portfolio_snapshot", "snapshot_date", "run_id", critical=True),
    )

    def __init__(self, session: Session):
        self.session = session

    def build(
        self,
        *,
        project_root: Path,
        report_date: date | None,
        campaign_config_path: Path,
        execution_context: str,
        output_root: Path,
        detail_limit: int = 50,
    ) -> dict[str, Any]:
        project_root = project_root.resolve()
        if not output_root.is_absolute():
            output_root = project_root / output_root
        campaign_config_path = self._resolve_project_path(project_root, campaign_config_path)

        resolved_report_date = report_date or self._resolve_report_date()
        generated_at = datetime.utcnow().isoformat()
        runtime_overview = self._build_runtime_overview(project_root=project_root)
        campaigns_all = self._load_campaigns(campaign_config_path)
        production_campaigns = self._filter_campaigns(campaigns_all, execution_context=execution_context)

        signal_as_of_date = self._resolve_signal_as_of_date(resolved_report_date)
        waterline = self._build_waterline(
            report_date=resolved_report_date,
            signal_as_of_date=signal_as_of_date,
        )
        data_refresh_summary = self._build_data_refresh_summary(report_date=resolved_report_date)
        feature_readiness = self._build_feature_readiness(
            report_date=resolved_report_date,
            signal_as_of_date=signal_as_of_date,
        )
        campaign_reports = [
            self._build_campaign_section(
                project_root=project_root,
                campaign=campaign,
                report_date=resolved_report_date,
                detail_limit=detail_limit,
            )
            for campaign in production_campaigns
        ]
        next_trade_date = self._resolve_next_trade_date(resolved_report_date)
        next_trade_plan = self._build_next_trade_plan(
            report_date=resolved_report_date,
            signal_as_of_date=signal_as_of_date,
            next_trade_date=next_trade_date,
            campaign_reports=campaign_reports,
            detail_limit=detail_limit,
        )
        used_date_guard = self._build_used_date_guard(
            report_date=resolved_report_date,
            signal_as_of_date=signal_as_of_date,
            waterline=waterline,
            campaign_reports=campaign_reports,
        )
        market_context = self._build_market_context(
            report_date=resolved_report_date,
            campaign_reports=campaign_reports,
            detail_limit=detail_limit,
        )
        return_attribution = self._build_return_attribution(
            campaign_reports=campaign_reports,
            market_context=market_context,
        )
        artifact_index = self._build_artifact_index(
            project_root=project_root,
            campaigns=production_campaigns,
            report_date=resolved_report_date,
        )
        checks = self._build_checks(
            waterline=waterline,
            production_campaigns=production_campaigns,
            campaign_reports=campaign_reports,
            artifact_index=artifact_index,
            used_date_guard=used_date_guard,
        )
        overall_status = self._derive_overall_status(checks)

        payload = {
            "report_type": "production_daily_observation_report",
            "execution_context": "production_daily_run",
            "report_context": "production_daily_observation",
            "paper_campaign_context": execution_context,
            "daily_profile": runtime_overview.get("daily_profile"),
            "git_commit": runtime_overview.get("git_commit"),
            "git_branch": runtime_overview.get("git_branch"),
            "git_dirty": runtime_overview.get("git_dirty"),
            "git_commit_status": runtime_overview.get("git_commit_status"),
            "docker_container": runtime_overview.get("docker_container"),
            "docker_image_id": runtime_overview.get("docker_image_id"),
            "docker_image_digest": runtime_overview.get("docker_image_digest"),
            "container_started_at": runtime_overview.get("container_started_at"),
            "runtime_command": runtime_overview.get("runtime_command"),
            "database": runtime_overview.get("database"),
            "runtime_overview": runtime_overview,
            "report_date": resolved_report_date,
            "generated_at": generated_at,
            "project_root": str(project_root),
            "campaign_config_path": str(campaign_config_path),
            "campaign_count": len(campaigns_all),
            "production_campaign_count": len(production_campaigns),
            "overall_status": overall_status,
            "signal_as_of_date": signal_as_of_date,
            "next_trade_date": next_trade_date,
            "next_trade_plan": next_trade_plan,
            "used_date_guard": used_date_guard,
            "waterline": waterline,
            "data_refresh_summary": data_refresh_summary,
            "feature_readiness": feature_readiness,
            "market_context": market_context,
            "return_attribution": return_attribution,
            "campaigns": campaign_reports,
            "artifact_index": artifact_index,
            "checks": checks,
            "observation_notes": self._build_observation_notes(
                overall_status=overall_status,
                waterline=waterline,
                market_context=market_context,
                campaign_reports=campaign_reports,
                artifact_index=artifact_index,
            ),
        }
        payload["daily_conclusion"] = self._build_daily_conclusion_summary(payload)
        payload["next_trade_plan_sla"] = self._build_next_trade_plan_sla(payload)
        payload["buy_price_quality"] = self._build_buy_price_quality(payload)
        payload["daily_diff"] = self._build_daily_diff(
            project_root=project_root,
            output_root=output_root,
            report_date=resolved_report_date,
            current_payload=payload,
        )
        payload["artifact_integrity"] = self._build_artifact_integrity(
            project_root=project_root,
            artifact_index=artifact_index,
        )
        payload["report_self_check"] = self._build_report_self_check(payload)
        payload["action_priority"] = self._build_action_priority(payload)
        payload["daily_control_panel"] = self._build_daily_control_panel(payload)
        payload["manual_review_checklist"] = self._build_manual_review_checklist(payload)

        output_dir = output_root / resolved_report_date.isoformat()
        latest_dir = output_root / "latest"
        output_dir.mkdir(parents=True, exist_ok=True)
        latest_dir.mkdir(parents=True, exist_ok=True)

        stem = f"production_daily_observation_{resolved_report_date.isoformat()}"
        json_path = output_dir / f"{stem}.json"
        md_path = output_dir / f"{stem}.md"
        sources_path = output_dir / f"{stem}_sources.csv"
        artifacts_path = output_dir / f"{stem}_artifacts.csv"

        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=self._json_default),
            encoding="utf-8",
        )
        md_path.write_text(self._render_markdown(payload), encoding="utf-8")
        self._write_csv(sources_path, self._source_rows(payload))
        self._write_csv(artifacts_path, artifact_index)

        latest_json = latest_dir / "production_daily_observation_latest.json"
        latest_md = latest_dir / "production_daily_observation_latest.md"
        latest_sources = latest_dir / "production_daily_observation_latest_sources.csv"
        latest_artifacts = latest_dir / "production_daily_observation_latest_artifacts.csv"
        shutil.copyfile(json_path, latest_json)
        shutil.copyfile(md_path, latest_md)
        shutil.copyfile(sources_path, latest_sources)
        shutil.copyfile(artifacts_path, latest_artifacts)

        payload["files"] = {
            "json": str(json_path),
            "markdown": str(md_path),
            "sources_csv": str(sources_path),
            "artifacts_csv": str(artifacts_path),
            "latest_json": str(latest_json),
            "latest_markdown": str(latest_md),
            "latest_sources_csv": str(latest_sources),
            "latest_artifacts_csv": str(latest_artifacts),
        }
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=self._json_default),
            encoding="utf-8",
        )
        shutil.copyfile(json_path, latest_json)
        return payload

    def _resolve_report_date(self) -> date:
        candidates = [
            ("trading_paper_portfolio_snapshot", "snapshot_date"),
            ("core_daily_bar", "trade_date"),
        ]
        for table_name, column_name in candidates:
            value = self._safe_scalar(f"select max({column_name}) from public.{table_name}")
            resolved = self._to_date(value)
            if resolved is not None:
                return resolved
        return date.today()

    @staticmethod
    def _resolve_project_path(project_root: Path, path: Path) -> Path:
        return path if path.is_absolute() else project_root / path

    def _build_runtime_overview(self, *, project_root: Path) -> dict[str, Any]:
        """Return production daily runtime metadata without changing runtime behavior."""
        git_commit = self._resolve_git_commit(project_root)
        git_branch = self._resolve_git_branch(project_root)
        git_dirty = self._resolve_git_dirty(project_root)
        docker_image_id = self._first_env(
            "SQV2_DOCKER_IMAGE_ID",
            "DOCKER_IMAGE_ID",
            "IMAGE_ID",
            "CONTAINER_IMAGE_ID",
        )
        docker_image_digest = self._first_env(
            "SQV2_DOCKER_IMAGE_DIGEST",
            "DOCKER_IMAGE_DIGEST",
            "IMAGE_DIGEST",
            "CONTAINER_IMAGE_DIGEST",
        )
        commit_unknown = str(git_commit or "").startswith("UNKNOWN")
        return {
            "daily_profile": os.environ.get("SQV2_DAILY_PROFILE") or "runtime",
            "git_commit": git_commit,
            "git_branch": git_branch,
            "git_dirty": git_dirty,
            "git_commit_status": "WARN" if commit_unknown else "PASS",
            "docker_container": os.environ.get("HOSTNAME") or socket.gethostname(),
            "docker_image_id": docker_image_id,
            "docker_image_digest": docker_image_digest,
            "container_started_at": self._container_started_at(),
            "runtime_command": self._runtime_command(),
            "database": self._database_label(),
            "traceability_status": "WARN" if commit_unknown else "PASS",
            "traceability_reason": "git_commit_unavailable_in_runtime" if commit_unknown else "git_commit_resolved",
        }

    @staticmethod
    def _first_env(*names: str) -> str | None:
        for name in names:
            value = os.environ.get(name)
            if value:
                return value
        return None

    @classmethod
    def _resolve_git_commit(cls, project_root: Path) -> str:
        env_commit = cls._first_env(
            "SQV2_GIT_COMMIT",
            "GIT_COMMIT",
            "GIT_SHA",
            "SOURCE_COMMIT",
            "COMMIT_SHA",
            "IMAGE_COMMIT",
            "BUILD_COMMIT",
        )
        if env_commit:
            return str(env_commit).strip()
        commit = cls._run_git(project_root, ["rev-parse", "--short", "HEAD"])
        if commit:
            return commit
        return "UNKNOWN_NO_GIT_METADATA"

    @classmethod
    def _resolve_git_branch(cls, project_root: Path) -> str | None:
        env_branch = cls._first_env("SQV2_GIT_BRANCH", "GIT_BRANCH", "BRANCH_NAME", "SOURCE_BRANCH")
        if env_branch:
            return str(env_branch).strip()
        branch = cls._run_git(project_root, ["rev-parse", "--abbrev-ref", "HEAD"])
        return branch or None

    @classmethod
    def _resolve_git_dirty(cls, project_root: Path) -> str:
        status = cls._run_git(project_root, ["status", "--short"])
        if status is None:
            return "UNKNOWN"
        return "true" if status.strip() else "false"

    @staticmethod
    def _run_git(project_root: Path, args: list[str]) -> str | None:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=str(project_root),
                check=False,
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode != 0:
                return None
            value = (result.stdout or "").strip()
            return value or None
        except Exception:
            return None

    @staticmethod
    def _container_started_at() -> str | None:
        try:
            proc_1 = Path("/proc/1")
            if proc_1.exists():
                return datetime.utcfromtimestamp(proc_1.stat().st_ctime).isoformat()
        except Exception:
            return None
        return None

    @staticmethod
    def _runtime_command() -> str | None:
        try:
            command = " ".join(str(part) for part in sys.argv if part is not None).strip()
            return command or None
        except Exception:
            return None

    @staticmethod
    def _database_label() -> str | None:
        url = os.environ.get("V2_SQLALCHEMY_URL") or os.environ.get("SQLALCHEMY_DATABASE_URL")
        if not url:
            return None
        # Avoid leaking credentials. Keep only host/database level context.
        text_url = str(url)
        if "@" in text_url:
            text_url = text_url.split("@", 1)[1]
        return text_url

    def _load_campaigns(self, campaign_config_path: Path) -> list[dict[str, Any]]:
        if not campaign_config_path.exists():
            return []
        try:
            data = json.loads(campaign_config_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        if isinstance(data, list):
            return [dict(item) for item in data if isinstance(item, dict)]
        if isinstance(data, dict) and isinstance(data.get("campaigns"), list):
            return [dict(item) for item in data["campaigns"] if isinstance(item, dict)]
        return []

    @staticmethod
    def _filter_campaigns(campaigns: list[dict[str, Any]], *, execution_context: str) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        for campaign in campaigns:
            if str(campaign.get("status") or "").upper() != "ACTIVE":
                continue
            if str(campaign.get("execution_context") or "") != execution_context:
                continue
            selected.append(campaign)
        return selected

    def _resolve_signal_as_of_date(self, report_date: date) -> date:
        previous_trade_date = self._safe_scalar(
            """
            select previous_trade_date
            from public.meta_trading_calendar
            where trade_date = :report_date
            limit 1
            """,
            {"report_date": report_date},
        )
        resolved = self._to_date(previous_trade_date)
        if resolved is not None:
            return resolved

        fallback = self._safe_scalar(
            """
            select max(trade_date)
            from public.meta_trading_calendar
            where is_open = true
              and trade_date < :report_date
            """,
            {"report_date": report_date},
        )
        resolved = self._to_date(fallback)
        return resolved or report_date

    def _build_waterline(self, *, report_date: date, signal_as_of_date: date) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for spec in self.WATERLINE_SPECS:
            row: dict[str, Any] = {
                "table_name": spec.table_name,
                "date_column": spec.date_column,
                "run_id_column": spec.run_id_column,
                "critical": spec.critical,
                "freshness_basis": spec.freshness_basis,
                "expected_date": signal_as_of_date if spec.freshness_basis == "signal_as_of_date" else report_date,
                "rows": None,
                "max_date": None,
                "max_run_id": None,
                "status": "WARN",
                "reason": "not_checked",
            }
            try:
                select_parts = ["count(*) as rows", f"max({spec.date_column}) as max_date"]
                if spec.run_id_column:
                    select_parts.append(f"max({spec.run_id_column}) as max_run_id")
                sql = f"select {', '.join(select_parts)} from public.{spec.table_name}"
                db_row = self.session.execute(text(sql)).mappings().one()
                row["rows"] = db_row.get("rows")
                row["max_date"] = self._to_date(db_row.get("max_date"))
                if spec.run_id_column:
                    row["max_run_id"] = db_row.get("max_run_id")
                max_date = row["max_date"]
                expected_date = row["expected_date"]
                if max_date is None:
                    row["status"] = "FAIL" if spec.critical else "WARN"
                    row["reason"] = "no_date"
                elif max_date >= expected_date:
                    row["status"] = "PASS"
                    row["reason"] = f"fresh_for_{spec.freshness_basis}:{max_date}>={expected_date}"
                else:
                    row["status"] = "FAIL" if spec.critical else "WARN"
                    row["reason"] = f"max_date_before_{spec.freshness_basis}:{max_date}<{expected_date}"
            except Exception as exc:
                row["status"] = "FAIL" if spec.critical else "WARN"
                row["reason"] = f"query_failed:{type(exc).__name__}:{exc}"
            rows.append(row)
        rows.extend(self._build_reference_data_waterline())
        return rows

    def _build_reference_data_waterline(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        try:
            tag_row = self.session.execute(
                text(
                    """
                    select
                        count(*) as rows,
                        count(*) filter (where tag_type like 'SW_INDUSTRY%') as industry_tag_rows,
                        count(*) filter (where tag_type = 'CONCEPT_EM') as concept_tag_rows
                    from public.tag
                    """
                )
            ).mappings().one()
            tag_count = self._optional_int(tag_row.get("rows")) or 0
            rows.append({
                "table_name": "tag",
                "date_column": None,
                "run_id_column": None,
                "critical": False,
                "freshness_basis": "reference_data",
                "expected_date": None,
                "rows": tag_row.get("rows"),
                "max_date": None,
                "max_run_id": None,
                "status": "PASS" if tag_count > 0 else "WARN",
                "reason": f"industry_tags={tag_row.get('industry_tag_rows')},concept_tags={tag_row.get('concept_tag_rows')}",
            })
        except Exception as exc:
            rows.append({
                "table_name": "tag",
                "date_column": None,
                "run_id_column": None,
                "critical": False,
                "freshness_basis": "reference_data",
                "expected_date": None,
                "rows": None,
                "max_date": None,
                "max_run_id": None,
                "status": "WARN",
                "reason": f"query_failed:{type(exc).__name__}:{exc}",
            })
        try:
            instrument_tag_row = self.session.execute(
                text(
                    """
                    select
                        count(*) as rows,
                        max(effective_from) as max_effective_from,
                        max(effective_to) as max_effective_to
                    from public.instrument_tag
                    """
                )
            ).mappings().one()
            row_count = self._optional_int(instrument_tag_row.get("rows")) or 0
            rows.append({
                "table_name": "instrument_tag",
                "date_column": "effective_from",
                "run_id_column": None,
                "critical": False,
                "freshness_basis": "reference_data",
                "expected_date": None,
                "rows": instrument_tag_row.get("rows"),
                "max_date": self._to_date(instrument_tag_row.get("max_effective_from")),
                "max_run_id": None,
                "status": "PASS" if row_count > 0 else "WARN",
                "reason": f"max_effective_from={instrument_tag_row.get('max_effective_from')}",
            })
        except Exception as exc:
            rows.append({
                "table_name": "instrument_tag",
                "date_column": "effective_from",
                "run_id_column": None,
                "critical": False,
                "freshness_basis": "reference_data",
                "expected_date": None,
                "rows": None,
                "max_date": None,
                "max_run_id": None,
                "status": "WARN",
                "reason": f"query_failed:{type(exc).__name__}:{exc}",
            })
        return rows

    def _build_data_refresh_summary(self, *, report_date: date, limit: int = 15) -> dict[str, Any]:
        try:
            rows = self._rows(
                """
                select
                    sync_job_code,
                    theme_code,
                    dataset_code,
                    provider_name,
                    sync_mode,
                    partition_from,
                    partition_to,
                    status,
                    stats_json,
                    started_at,
                    finished_at
                from public.data_sync_run
                where coalesce(partition_to, partition_from, finished_at::date, started_at::date) <= :report_date
                order by finished_at desc nulls last, started_at desc nulls last, id desc
                limit :limit
                """,
                {"report_date": report_date, "limit": limit},
            )
        except Exception as exc:
            return {"status": "WARN", "reason": f"query_failed:{type(exc).__name__}:{exc}", "rows": []}

        normalized: list[dict[str, Any]] = []
        for row in rows:
            stats = self._coerce_json_dict(row.get("stats_json"))
            failed_rows = self._stats_value(stats, ("failed_rows", "fail_rows", "error_rows", "failed", "errors"))
            normalized.append({
                "refresh_module": row.get("sync_job_code") or row.get("dataset_code") or row.get("theme_code"),
                "dataset_code": row.get("dataset_code"),
                "provider": row.get("provider_name"),
                "date_from": row.get("partition_from"),
                "date_to": row.get("partition_to"),
                "status": row.get("status"),
                "inserted_rows": self._stats_value(stats, ("inserted_rows", "insert_rows", "created_rows", "created", "inserted")),
                "updated_rows": self._stats_value(stats, ("updated_rows", "update_rows", "updated")),
                "skipped_rows": self._stats_value(stats, ("skipped_rows", "skip_rows", "skipped")),
                "failed_rows": failed_rows,
                "provider_fallback": self._stats_value(stats, ("provider_fallback", "fallback_provider", "fallback", "fallback_used")),
                "key_error": self._stats_value(stats, ("error", "key_error", "last_error", "message")),
            })
        if not normalized:
            return {"status": "WARN", "reason": "no_recent_data_sync_run_rows", "rows": []}
        has_failure = any(str(row.get("status") or "").upper() in {"FAIL", "FAILED", "ERROR"} or (self._optional_int(row.get("failed_rows")) or 0) > 0 for row in normalized)
        return {"status": "WARN" if has_failure else "PASS", "reason": f"rows={len(normalized)}", "rows": normalized}

    def _build_feature_readiness(self, *, report_date: date, signal_as_of_date: date) -> dict[str, Any]:
        try:
            row = self._one_or_none(
                """
                with
                feature_date as (
                    select max(trade_date) as trade_date from public.analytics_feature_snapshot where trade_date <= :signal_as_of_date
                ),
                factor_date as (
                    select max(trade_date) as trade_date from public.analytics_instrument_factor_snapshot where trade_date <= :signal_as_of_date
                ),
                indicator_date as (
                    select max(trade_date) as trade_date from public.analytics_instrument_indicator_snapshot where trade_date <= :signal_as_of_date
                ),
                active_instruments as (
                    select count(*) as universe_size from public.meta_instrument where is_active = true
                )
                select
                    (select trade_date from feature_date) as feature_date,
                    (select universe_size from active_instruments) as universe_size,
                    (select count(distinct instrument_id) from public.analytics_feature_snapshot where trade_date = (select trade_date from feature_date)) as valid_instrument_count,
                    (select count(*) from public.analytics_feature_snapshot where trade_date = (select trade_date from feature_date)) as feature_rows,
                    (select trade_date from factor_date) as factor_date,
                    (select count(*) from public.analytics_instrument_factor_snapshot where trade_date = (select trade_date from factor_date)) as factor_rows,
                    (select trade_date from indicator_date) as indicator_date,
                    (select count(*) from public.analytics_instrument_indicator_snapshot where trade_date = (select trade_date from indicator_date)) as indicator_rows
                """,
                {"signal_as_of_date": signal_as_of_date},
            ) or {}
        except Exception as exc:
            return {"feature_status": "WARN", "reason": f"query_failed:{type(exc).__name__}:{exc}"}

        universe_size = self._optional_int(row.get("universe_size")) or 0
        valid_count = self._optional_int(row.get("valid_instrument_count")) or 0
        missing_count = max(universe_size - valid_count, 0) if universe_size else None
        feature_date = self._to_date(row.get("feature_date"))
        factor_rows = self._optional_int(row.get("factor_rows")) or 0
        indicator_rows = self._optional_int(row.get("indicator_rows")) or 0
        feature_status = "PASS" if feature_date and feature_date >= signal_as_of_date and valid_count > 0 and factor_rows > 0 and indicator_rows > 0 else "WARN"
        return {
            "feature_date": feature_date,
            "universe_size": universe_size,
            "valid_instrument_count": valid_count,
            "excluded_instrument_count": missing_count,
            "indicator_rows": row.get("indicator_rows"),
            "factor_rows": row.get("factor_rows"),
            "feature_rows": row.get("feature_rows"),
            "missing_feature_count": missing_count,
            "factor_date": self._to_date(row.get("factor_date")),
            "indicator_date": self._to_date(row.get("indicator_date")),
            "feature_status": feature_status,
            "reason": f"feature_date={feature_date},signal_as_of_date={signal_as_of_date},valid={valid_count},universe={universe_size}",
        }

    def _build_campaign_section(
        self,
        *,
        project_root: Path,
        campaign: dict[str, Any],
        report_date: date,
        detail_limit: int,
    ) -> dict[str, Any]:
        portfolio_id = self._optional_int(campaign.get("portfolio_id"))
        section: dict[str, Any] = {
            "campaign_code": campaign.get("campaign_code"),
            "campaign_name": campaign.get("campaign_name"),
            "strategy_code": campaign.get("strategy_code"),
            "strategy_version_code": campaign.get("strategy_version_code"),
            "execution_context": campaign.get("execution_context"),
            "validation_stage": campaign.get("validation_stage"),
            "validation_scope": campaign.get("validation_scope"),
            "portfolio_id": portfolio_id,
            "target_count": campaign.get("target_count"),
            "status": "WARN",
            "reason": None,
            "selection_summary": None,
            "selected_instruments": [],
            "trade_summary": None,
            "trade_details": [],
            "ledger_summary": [],
            "runtime_observation": {},
            "snapshot": None,
            "positions_preview": [],
            "top_gainers": [],
            "top_losers": [],
            "risk_metrics": {},
            "campaign_risk_checks": [],
            "artifact_files": self._campaign_artifacts(project_root, str(campaign.get("campaign_code") or "")),
        }
        if portfolio_id is None:
            section["reason"] = "missing_portfolio_id"
            return section

        section["selection_summary"] = self._latest_selection_summary(
            portfolio_id=portfolio_id,
            report_date=report_date,
            target_count=self._optional_int(campaign.get("target_count")) or 30,
        )
        target_run_id = ((section.get("selection_summary") or {}).get("target_run_id"))
        if target_run_id is not None:
            section["selected_instruments"] = self._selected_instruments(
                portfolio_id=portfolio_id,
                target_run_id=int(target_run_id),
                limit=detail_limit,
            )
        section["trade_summary"] = self._latest_trade_summary(portfolio_id=portfolio_id, report_date=report_date)
        trade_summary = section.get("trade_summary") or {}
        orders = trade_summary.get("orders") if isinstance(trade_summary, dict) else {}
        fills = trade_summary.get("fills") if isinstance(trade_summary, dict) else {}
        order_run_id = (orders or {}).get("order_run_id")
        fill_run_id = (fills or {}).get("fill_run_id")
        if order_run_id is not None:
            section["trade_details"] = self._trade_details(
                portfolio_id=portfolio_id,
                order_run_id=int(order_run_id),
                fill_run_id=self._optional_int(fill_run_id),
                limit=detail_limit,
            )
        section["ledger_summary"] = self._ledger_summary(portfolio_id=portfolio_id, report_date=report_date)

        section["snapshot"] = self._latest_snapshot(portfolio_id=portfolio_id, report_date=report_date)
        snapshot = section.get("snapshot") or {}
        position_run_id = snapshot.get("position_run_id") or snapshot.get("snapshot_run_id")
        if position_run_id is not None:
            section["positions_preview"] = self._positions_preview(
                portfolio_id=portfolio_id,
                position_run_id=int(position_run_id),
                total_equity=snapshot.get("total_equity"),
                limit=detail_limit,
            )
            section["risk_metrics"] = self._position_risk_metrics(
                portfolio_id=portfolio_id,
                position_run_id=int(position_run_id),
                total_equity=snapshot.get("total_equity"),
            )
            section["top_gainers"] = self._position_extremes(
                portfolio_id=portfolio_id,
                position_run_id=int(position_run_id),
                order="gain",
                limit=5,
            )
            section["top_losers"] = self._position_extremes(
                portfolio_id=portfolio_id,
                position_run_id=int(position_run_id),
                order="loss",
                limit=5,
            )
            section["trade_lifecycle"] = self._trade_lifecycle_observation(
                portfolio_id=portfolio_id,
                report_date=report_date,
                position_run_id=int(position_run_id),
                order_run_id=self._optional_int(order_run_id),
                selection_summary=section.get("selection_summary") or {},
                trade_summary=section.get("trade_summary") or {},
                snapshot=snapshot,
                limit=10,
            )

        section["runtime_observation"] = self._campaign_runtime_observation(
            project_root=project_root,
            campaign_code=str(campaign.get("campaign_code") or ""),
            report_date=report_date,
            selection_summary=section.get("selection_summary") or {},
            trade_summary=section.get("trade_summary") or {},
            snapshot=section.get("snapshot") or {},
        )

        section["campaign_risk_checks"] = self._campaign_risk_checks(section)

        checks = []
        if section["selection_summary"]:
            checks.append("selection")
        if section["snapshot"]:
            checks.append("snapshot")
        if section["trade_summary"]:
            checks.append("trade")
        risk_statuses = [str(item.get("status") or "WARN") for item in section.get("campaign_risk_checks") or []]
        if len(checks) >= 2:
            section["status"] = "PASS"
            section["reason"] = "production_campaign_observable"
        elif checks:
            section["status"] = "WARN"
            section["reason"] = f"partial_observation:{','.join(checks)}"
        else:
            section["status"] = "FAIL"
            section["reason"] = "no_recent_campaign_runtime_data"

        if section["status"] == "PASS" and any(status == "WARN" for status in risk_statuses):
            section["status"] = "WARN"
            section["reason"] = "production_campaign_observable_with_risk_warning"
        if any(status == "FAIL" for status in risk_statuses):
            section["status"] = "FAIL"
            section["reason"] = "production_campaign_risk_check_failed"
        return section

    def _latest_selection_summary(self, *, portfolio_id: int, report_date: date, target_count: int) -> dict[str, Any] | None:
        sql = """
        select
            t.run_id as target_run_id,
            t.portfolio_id,
            max(t.effective_date) as effective_date,
            max(t.source_signal_run_id) as source_signal_run_id,
            max(t.source_screen_request_id) as source_screen_request_id,
            count(*) as selected_count,
            min(t.rank_no) as min_target_rank,
            max(t.rank_no) as max_target_rank,
            min(t.score) as min_target_score,
            max(t.score) as max_target_score,
            min(ss.rank_in_batch) as min_source_rank,
            max(ss.rank_in_batch) as max_source_rank,
            count(*) filter (where ss.rank_in_batch <= :target_count) as rank_in_scope_rows,
            count(*) filter (where ss.rank_in_batch > :target_count) as rank_out_of_scope_rows
        from public.trading_paper_target_position t
        left join public.strategy_signal ss on ss.id = t.strategy_signal_id
        where t.portfolio_id = :portfolio_id
          and t.effective_date <= :report_date
          and t.run_id = (
              select max(run_id)
              from public.trading_paper_target_position
              where portfolio_id = :portfolio_id
                and effective_date <= :report_date
          )
        group by t.run_id, t.portfolio_id
        """
        summary = self._one_or_none(sql, {"portfolio_id": portfolio_id, "report_date": report_date, "target_count": target_count})
        if summary:
            source_signal_run_id = summary.get("source_signal_run_id")
            if source_signal_run_id is not None:
                summary["candidate_count"] = self._safe_scalar(
                    "select count(*) from public.strategy_signal where run_id = :run_id",
                    {"run_id": source_signal_run_id},
                )
            rank_out = self._optional_int(summary.get("rank_out_of_scope_rows")) or 0
            selected_count = self._optional_int(summary.get("selected_count")) or 0
            rank_in = self._optional_int(summary.get("rank_in_scope_rows")) or 0
            summary["rank_scope_check"] = bool(selected_count and rank_out == 0 and rank_in == selected_count)
        return summary

    def _selected_instruments(self, *, portfolio_id: int, target_run_id: int, limit: int) -> list[dict[str, Any]]:
        sql = """
        select
            t.instrument_id,
            mi.instrument_code,
            mi.symbol,
            mi.display_name,
            t.rank_no,
            t.score,
            t.target_weight,
            t.target_quantity,
            t.reason_code as target_reason_code,
            ss.rank_in_batch as source_rank,
            ss.raw_score as source_raw_score,
            ss.reason_code as signal_reason_code
        from public.trading_paper_target_position t
        left join public.strategy_signal ss on ss.id = t.strategy_signal_id
        left join public.meta_instrument mi on mi.id = t.instrument_id
        where t.portfolio_id = :portfolio_id
          and t.run_id = :target_run_id
        order by t.rank_no nulls last, t.score desc nulls last, t.instrument_id
        limit :limit
        """
        return self._rows(sql, {"portfolio_id": portfolio_id, "target_run_id": target_run_id, "limit": limit})

    def _latest_trade_summary(self, *, portfolio_id: int, report_date: date) -> dict[str, Any] | None:
        order_sql = """
        select run_id as order_run_id, max(effective_date) as effective_date,
               count(*) as order_count,
               count(*) filter (where upper(order_side) = 'BUY') as buy_order_count,
               count(*) filter (where upper(order_side) = 'SELL') as sell_order_count,
               count(*) filter (where upper(status) not in ('CREATED','ACCEPTED','FILLED')) as abnormal_order_count,
               string_agg(distinct nullif(price_fill_rule, ''), ',') as entry_policy,
               string_agg(distinct nullif(order_type, ''), ',') as order_type_policy,
               sum(order_quantity) as total_order_quantity,
               sum(estimated_gross_amount) as total_estimated_gross_amount,
               sum(estimated_fee) as total_estimated_fee,
               sum(estimated_net_amount) as total_estimated_net_amount
        from public.trading_paper_order
        where portfolio_id = :portfolio_id
          and effective_date <= :report_date
          and run_id = (
              select max(run_id) from public.trading_paper_order
              where portfolio_id = :portfolio_id and effective_date <= :report_date
          )
        group by run_id
        """
        fill_sql = """
        select run_id as fill_run_id, max(fill_date) as fill_date,
               count(*) as fill_count,
               count(*) filter (where upper(fill_status) not in ('FILLED','SUCCESS','COMPLETED')) as abnormal_fill_count,
               sum(fill_quantity) as total_fill_quantity,
               sum(gross_amount) as gross_amount,
               sum(total_fee_amount) as total_fee_amount,
               sum(net_amount) as net_amount,
               sum(cash_delta) as cash_delta,
               string_agg(distinct nullif(fill_rule, ''), ',') as fill_policy,
               string_agg(distinct nullif(price_source, ''), ',') as fill_price_source
        from public.trading_paper_fill
        where portfolio_id = :portfolio_id
          and fill_date <= :report_date
          and run_id = (
              select max(run_id) from public.trading_paper_fill
              where portfolio_id = :portfolio_id and fill_date <= :report_date
          )
        group by run_id
        """
        orders = self._one_or_none(order_sql, {"portfolio_id": portfolio_id, "report_date": report_date})
        fills = self._one_or_none(fill_sql, {"portfolio_id": portfolio_id, "report_date": report_date})
        if not orders and not fills:
            return None
        return {"orders": orders, "fills": fills}

    def _latest_snapshot(self, *, portfolio_id: int, report_date: date) -> dict[str, Any] | None:
        sql = """
        select
            run_id as snapshot_run_id,
            portfolio_id,
            snapshot_date,
            position_run_id,
            fill_run_id,
            cash_balance,
            market_value,
            total_equity,
            gross_exposure,
            net_exposure,
            holding_count,
            daily_pnl,
            daily_return,
            cumulative_pnl,
            cumulative_return,
            turnover_amount,
            turnover_rate,
            cash_delta,
            total_cost,
            unrealized_pnl,
            realized_pnl,
            open_position_count,
            closed_position_count
        from public.trading_paper_portfolio_snapshot
        where portfolio_id = :portfolio_id
          and snapshot_date <= :report_date
        order by snapshot_date desc, run_id desc
        limit 1
        """
        return self._one_or_none(sql, {"portfolio_id": portfolio_id, "report_date": report_date})

    def _positions_preview(self, *, portfolio_id: int, position_run_id: int, total_equity: Any, limit: int) -> list[dict[str, Any]]:
        sql = """
        select
            p.instrument_id,
            mi.instrument_code,
            mi.symbol,
            mi.display_name,
            p.quantity,
            p.avg_cost,
            p.market_price,
            p.market_value,
            p.unrealized_pnl,
            p.realized_pnl,
            p.total_pnl,
            p.position_status
        from public.trading_paper_position p
        left join public.meta_instrument mi on mi.id = p.instrument_id
        where p.portfolio_id = :portfolio_id
          and p.run_id = :position_run_id
        order by p.market_value desc nulls last, p.instrument_id
        limit :limit
        """
        rows = self._rows(sql, {"portfolio_id": portfolio_id, "position_run_id": position_run_id, "limit": limit})
        for row in rows:
            row["position_weight"] = self._safe_ratio(row.get("market_value"), total_equity)
        return rows

    def _trade_details(self, *, portfolio_id: int, order_run_id: int, fill_run_id: int | None, limit: int) -> list[dict[str, Any]]:
        sql = """
        select
            o.id as order_id,
            o.run_id as order_run_id,
            o.order_date,
            o.effective_date,
            o.instrument_id,
            mi.instrument_code,
            mi.symbol,
            mi.display_name,
            o.order_side,
            o.order_type,
            o.price_fill_rule,
            o.target_quantity,
            o.order_quantity,
            o.estimated_price,
            o.estimated_gross_amount,
            o.estimated_fee,
            o.estimated_net_amount,
            o.status as order_status,
            o.reject_reason,
            f.id as fill_id,
            f.run_id as fill_run_id,
            f.fill_date,
            f.fill_price,
            f.fill_quantity,
            f.gross_amount,
            f.total_fee_amount,
            f.net_amount,
            f.cash_delta,
            f.price_source,
            f.fill_rule,
            f.fill_status,
            t.rank_no,
            t.target_weight,
            t.reason_code as target_reason_code,
            t.status_reason as target_status_reason,
            ss.rank_in_batch as source_rank,
            ss.reason_code as signal_reason_code
        from public.trading_paper_order o
        left join public.trading_paper_fill f
          on f.order_id = o.id
         and (:fill_run_id is null or f.run_id = :fill_run_id)
        left join public.trading_paper_target_position t on t.id = o.target_position_id
        left join public.strategy_signal ss on ss.id = t.strategy_signal_id
        left join public.meta_instrument mi on mi.id = o.instrument_id
        where o.portfolio_id = :portfolio_id
          and o.run_id = :order_run_id
        order by o.id
        limit :limit
        """
        rows = self._rows(
            sql,
            {
                "portfolio_id": portfolio_id,
                "order_run_id": order_run_id,
                "fill_run_id": fill_run_id,
                "limit": limit,
            },
        )
        for row in rows:
            reason_parts = self._trade_reason_parts(row)
            row["trade_reason_parts"] = reason_parts
            row["trade_reason_summary"] = self._trade_reason_summary(reason_parts)
            row["trade_reason"] = self._trade_reason(row)
            side = str(row.get("order_side") or "").upper()
            policy = self._dedupe_join([row.get("price_fill_rule"), row.get("fill_rule"), row.get("price_source")], separator=";")
            row["entry_policy"] = policy if side == "BUY" else None
            row["exit_policy"] = policy if side == "SELL" else None
        return rows

    def _campaign_runtime_observation(
        self,
        *,
        project_root: Path,
        campaign_code: str,
        report_date: date,
        selection_summary: dict[str, Any],
        trade_summary: dict[str, Any],
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        orders = trade_summary.get("orders") if isinstance(trade_summary, dict) else {}
        fills = trade_summary.get("fills") if isinstance(trade_summary, dict) else {}
        daily_artifact = project_root / "artifacts/m6_5/paper_campaign_daily" / f"{campaign_code}_{report_date.isoformat()}.json"
        artifact_payload: dict[str, Any] = {}
        artifact_campaign: dict[str, Any] = {}
        if daily_artifact.exists():
            try:
                artifact_payload = json.loads(daily_artifact.read_text(encoding="utf-8"))
                artifact_campaign = self._find_campaign_payload(artifact_payload, campaign_code) or {}
            except Exception as exc:
                artifact_payload = {"parse_error": f"{type(exc).__name__}:{exc}"}

        snapshot_date = self._to_date(snapshot.get("snapshot_date"))
        effective_date = self._to_date(selection_summary.get("effective_date"))
        fill_date = self._to_date((fills or {}).get("fill_date"))
        order_date = self._to_date((orders or {}).get("effective_date"))
        date_candidates = [x for x in (snapshot_date, effective_date, fill_date, order_date) if x is not None]
        latest_campaign_date = max(date_candidates) if date_candidates else None

        if latest_campaign_date == report_date:
            campaign_data_status = "CURRENT_REPORT_DATE"
        elif latest_campaign_date is None:
            campaign_data_status = "NO_RUNTIME_DATA"
        else:
            campaign_data_status = f"LATEST_CAMPAIGN_DATE_{latest_campaign_date.isoformat()}"

        artifact_action = self._first_present(
            artifact_campaign,
            artifact_payload,
            keys=("action", "planned_action", "runtime_action"),
        )
        artifact_status = self._first_present(
            artifact_campaign,
            artifact_payload,
            keys=("status", "overall_status", "daily_status"),
        )
        artifact_reason = self._first_present(
            artifact_campaign,
            artifact_payload,
            keys=("reason", "message", "status_reason"),
        )

        if not daily_artifact.exists():
            runtime_action = "NO_DAILY_ARTIFACT"
        elif artifact_action:
            runtime_action = str(artifact_action)
        elif latest_campaign_date == report_date:
            runtime_action = "OBSERVED_REPORT_DATE_DATA"
        else:
            runtime_action = "ARTIFACT_PRESENT"

        return {
            "runtime_action": runtime_action,
            "campaign_data_status": campaign_data_status,
            "latest_campaign_date": latest_campaign_date,
            "daily_artifact_path": str(daily_artifact.relative_to(project_root)) if daily_artifact.exists() else str(daily_artifact),
            "daily_artifact_exists": daily_artifact.exists(),
            "daily_artifact_status": artifact_status,
            "daily_artifact_reason": artifact_reason,
            "target_run_id": selection_summary.get("target_run_id"),
            "order_run_id": (orders or {}).get("order_run_id"),
            "fill_run_id": (fills or {}).get("fill_run_id"),
            "snapshot_run_id": snapshot.get("snapshot_run_id"),
            "position_run_id": snapshot.get("position_run_id") or snapshot.get("snapshot_run_id"),
            "note": "Campaign run ids are portfolio/campaign scoped. Waterline max_run_id is table-global and may belong to another portfolio or runtime step.",
        }

    @classmethod
    def _find_campaign_payload(cls, value: Any, campaign_code: str) -> dict[str, Any] | None:
        if not campaign_code:
            return None
        if isinstance(value, dict):
            if str(value.get("campaign_code") or "") == campaign_code:
                return value
            for child in value.values():
                found = cls._find_campaign_payload(child, campaign_code)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = cls._find_campaign_payload(child, campaign_code)
                if found is not None:
                    return found
        return None

    @staticmethod
    def _first_present(*payloads: dict[str, Any], keys: tuple[str, ...]) -> Any:
        for payload in payloads:
            if not isinstance(payload, dict):
                continue
            for key in keys:
                value = payload.get(key)
                if value not in (None, ""):
                    return value
        return None

    def _ledger_summary(self, *, portfolio_id: int, report_date: date) -> list[dict[str, Any]]:
        sql = """
        select
            event_type,
            reason_code,
            count(*) as rows,
            sum(quantity_delta) as total_quantity_delta,
            sum(cash_delta) as total_cash_delta,
            sum(amount_delta) as total_amount_delta
        from public.trading_paper_trade_ledger
        where portfolio_id = :portfolio_id
          and event_date = :report_date
        group by event_type, reason_code
        order by event_type, reason_code
        """
        return self._rows(sql, {"portfolio_id": portfolio_id, "report_date": report_date})

    def _position_risk_metrics(self, *, portfolio_id: int, position_run_id: int, total_equity: Any) -> dict[str, Any]:
        sql = """
        select
            count(*) as position_rows,
            count(*) filter (where upper(position_status) = 'OPEN') as open_position_rows,
            sum(case when total_pnl > 0 then 1 else 0 end) as profitable_position_rows,
            sum(case when total_pnl < 0 then 1 else 0 end) as losing_position_rows,
            max(market_value) as max_market_value,
            sum(market_value) as total_market_value,
            sum(total_pnl) as total_position_pnl,
            min(total_pnl) as min_position_pnl,
            max(total_pnl) as max_position_pnl
        from public.trading_paper_position
        where portfolio_id = :portfolio_id
          and run_id = :position_run_id
        """
        row = self._one_or_none(sql, {"portfolio_id": portfolio_id, "position_run_id": position_run_id}) or {}
        row["max_position_weight"] = self._safe_ratio(row.get("max_market_value"), total_equity)
        row["stock_exposure"] = self._safe_ratio(row.get("total_market_value"), total_equity)
        return row

    def _position_extremes(self, *, portfolio_id: int, position_run_id: int, order: str, limit: int) -> list[dict[str, Any]]:
        direction = "desc" if order == "gain" else "asc"
        sql = f"""
        select
            p.instrument_id,
            mi.instrument_code,
            mi.symbol,
            mi.display_name,
            p.quantity,
            p.market_value,
            p.total_pnl,
            p.position_status
        from public.trading_paper_position p
        left join public.meta_instrument mi on mi.id = p.instrument_id
        where p.portfolio_id = :portfolio_id
          and p.run_id = :position_run_id
        order by p.total_pnl {direction} nulls last, p.market_value desc nulls last
        limit :limit
        """
        return self._rows(sql, {"portfolio_id": portfolio_id, "position_run_id": position_run_id, "limit": limit})

    def _trade_lifecycle_observation(
        self,
        *,
        portfolio_id: int,
        report_date: date,
        position_run_id: int,
        order_run_id: int | None,
        selection_summary: dict[str, Any],
        trade_summary: dict[str, Any],
        snapshot: dict[str, Any],
        limit: int,
    ) -> dict[str, Any]:
        """Build production observation for trade lifecycle without pretending to be an exit-rule engine.

        Current production tables contain target/order/fill/position snapshots and optional risk_decision rows,
        but they do not yet materialize formal 20-trading-day exit, profit drawdown, stop-loss, or sell-signal
        lifecycle states. Keep this section explicit: observed facts are reported as OBSERVED; missing rule-backed
        lifecycle items are reported as NOT_EVALUATED.
        """
        orders = trade_summary.get("orders") if isinstance(trade_summary, dict) else {}
        fills = trade_summary.get("fills") if isinstance(trade_summary, dict) else {}
        sell_count = self._optional_int((orders or {}).get("sell_order_count")) or 0
        buy_count = self._optional_int((orders or {}).get("buy_order_count")) or 0
        selected_count = self._optional_int(selection_summary.get("selected_count")) or 0
        holding_count = self._optional_int(snapshot.get("holding_count")) or 0
        effective_date = self._to_date(selection_summary.get("effective_date"))
        snapshot_date = self._to_date(snapshot.get("snapshot_date")) or report_date

        rows_sql = """
        with current_pos as (
            select
                p.instrument_id,
                mi.instrument_code,
                mi.symbol,
                mi.display_name,
                p.position_date,
                p.quantity,
                p.avg_cost,
                p.market_price,
                p.market_value,
                p.total_pnl,
                p.position_status
            from public.trading_paper_position p
            left join public.meta_instrument mi on mi.id = p.instrument_id
            where p.portfolio_id = :portfolio_id
              and p.run_id = :position_run_id
        ),
        first_seen as (
            select
                instrument_id,
                min(position_date) as first_position_date
            from public.trading_paper_position
            where portfolio_id = :portfolio_id
              and quantity > 0
              and position_date <= :report_date
            group by instrument_id
        ),
        last_order as (
            select distinct on (instrument_id)
                instrument_id,
                effective_date as last_order_date,
                order_side as last_order_side,
                price_fill_rule as last_order_policy,
                status as last_order_status
            from public.trading_paper_order
            where portfolio_id = :portfolio_id
              and effective_date <= :report_date
            order by instrument_id, effective_date desc, run_id desc, id desc
        )
        select
            cp.instrument_id,
            cp.instrument_code,
            cp.symbol,
            cp.display_name,
            cp.position_date,
            fs.first_position_date,
            (cp.position_date - fs.first_position_date + 1) as calendar_holding_days_candidate,
            greatest(20 - (cp.position_date - fs.first_position_date + 1), 0) as calendar_days_to_20_candidate,
            cp.quantity,
            cp.avg_cost,
            cp.market_price,
            cp.market_value,
            cp.total_pnl,
            cp.position_status,
            lo.last_order_date,
            lo.last_order_side,
            lo.last_order_policy,
            lo.last_order_status
        from current_pos cp
        left join first_seen fs on fs.instrument_id = cp.instrument_id
        left join last_order lo on lo.instrument_id = cp.instrument_id
        order by calendar_holding_days_candidate desc nulls last, cp.market_value desc nulls last, cp.instrument_id
        limit :limit
        """
        details = self._rows(
            rows_sql,
            {
                "portfolio_id": portfolio_id,
                "position_run_id": position_run_id,
                "report_date": report_date,
                "limit": limit,
            },
        )
        all_rows = self._rows(
            rows_sql.replace("limit :limit", ""),
            {
                "portfolio_id": portfolio_id,
                "position_run_id": position_run_id,
                "report_date": report_date,
                "limit": 100000,
            },
        )
        holding_days_values = [
            self._optional_int(row.get("calendar_holding_days_candidate"))
            for row in all_rows
            if self._optional_int(row.get("calendar_holding_days_candidate")) is not None
        ]
        near_20_count = sum(1 for value in holding_days_values if value is not None and value >= 15)
        reached_20_count = sum(1 for value in holding_days_values if value is not None and value >= 20)
        open_count = sum(1 for row in all_rows if str(row.get("position_status") or "").upper() == "OPEN")
        winning_count = sum(1 for row in all_rows if (self._to_decimal_value(row.get("total_pnl")) or Decimal("0")) > 0)
        losing_count = sum(1 for row in all_rows if (self._to_decimal_value(row.get("total_pnl")) or Decimal("0")) < 0)

        risk_sql = """
        select
            count(*) as risk_decision_count,
            count(*) filter (where upper(coalesce(action_taken, '')) like '%REDUCE%' or upper(coalesce(decision_type, '')) like '%REDUCE%') as risk_reduce_count,
            count(*) filter (where upper(coalesce(action_taken, '')) like '%BLOCK%' or upper(coalesce(decision_type, '')) like '%BLOCK%') as risk_block_count,
            string_agg(distinct nullif(reason_code, ''), ',') as risk_reason_codes
        from public.risk_decision
        where portfolio_id = :portfolio_id
          and decision_date = :report_date
        """
        try:
            risk_decision = self._one_or_none(risk_sql, {"portfolio_id": portfolio_id, "report_date": report_date}) or {}
        except Exception as exc:
            risk_decision = {"query_error": f"{type(exc).__name__}:{exc}"}

        lifecycle_context = "FIRST_CHAIN" if selected_count and buy_count and sell_count == 0 and holding_count == buy_count else "DAILY_OBSERVATION"
        if order_run_id is None:
            lifecycle_context = "NO_ORDER_RUN"

        exit_checks = [
            {
                "check_name": "sell_order_observed",
                "status": "OBSERVED",
                "value": f"sell_count={sell_count}",
                "reason": "当日卖出订单数量；这只是已发生交易观察，不等同于完整卖点信号评估。",
            },
            {
                "check_name": "no_exit_positions",
                "status": "OBSERVED",
                "value": f"no_exit_count={open_count}",
                "reason": "当前 position_status=OPEN 的持仓继续纳入观察。",
            },
            {
                "check_name": "holding_days_candidate",
                "status": "CANDIDATE",
                "value": f"min={min(holding_days_values) if holding_days_values else None},max={max(holding_days_values) if holding_days_values else None},near_20={near_20_count},reached_20={reached_20_count}",
                "reason": "按当前持仓首次出现在 position 表的自然日候选值估算，不等同于正式 20 个交易日退出规则。",
            },
            {
                "check_name": "twenty_trading_day_exit",
                "status": "NOT_EVALUATED",
                "value": "not_materialized",
                "reason": "当前生产表未落地正式 20 个交易日退出规则状态；不能硬判定触发/未触发。",
            },
            {
                "check_name": "profit_drawdown_exit",
                "status": "NOT_EVALUATED",
                "value": "not_materialized",
                "reason": "当前生产表未落地持仓峰值收益/利润回撤阈值状态；不能硬判定触发/未触发。",
            },
            {
                "check_name": "stop_loss_exit",
                "status": "NOT_EVALUATED",
                "value": "not_materialized",
                "reason": "当前 active campaign 未提供正式止损阈值状态；不能硬判定触发/未触发。",
            },
            {
                "check_name": "risk_reduce_exit",
                "status": "OBSERVED" if risk_decision.get("query_error") is None else "WARN",
                "value": f"risk_reduce_count={self._optional_int(risk_decision.get('risk_reduce_count')) or 0}",
                "reason": risk_decision.get("query_error") or "来自 risk_decision 当日记录的风控减仓候选观察。",
            },
        ]

        return {
            "scope": "production_observation_lifecycle_skeleton_not_exit_rule_engine",
            "lifecycle_context": lifecycle_context,
            "target_run_id": selection_summary.get("target_run_id"),
            "order_run_id": (orders or {}).get("order_run_id"),
            "fill_run_id": (fills or {}).get("fill_run_id"),
            "position_run_id": position_run_id,
            "effective_date": effective_date,
            "snapshot_date": snapshot_date,
            "buy_count": buy_count,
            "sell_count": sell_count,
            "current_position_count": len(all_rows),
            "open_position_count": open_count,
            "no_exit_count": open_count if sell_count == 0 else max(open_count - sell_count, 0),
            "winning_position_count": winning_count,
            "losing_position_count": losing_count,
            "calendar_holding_days_min": min(holding_days_values) if holding_days_values else None,
            "calendar_holding_days_max": max(holding_days_values) if holding_days_values else None,
            "near_20_calendar_day_count": near_20_count,
            "reached_20_calendar_day_count": reached_20_count,
            "risk_decision": risk_decision,
            "exit_checks": exit_checks,
            "details": details,
        }

    def _campaign_risk_checks(self, section: dict[str, Any]) -> list[dict[str, Any]]:
        selection = section.get("selection_summary") or {}
        trade = section.get("trade_summary") or {}
        orders = trade.get("orders") if isinstance(trade, dict) else {}
        fills = trade.get("fills") if isinstance(trade, dict) else {}
        snapshot = section.get("snapshot") or {}
        risk = section.get("risk_metrics") or {}

        selected_count = self._optional_int(selection.get("selected_count"))
        order_count = self._optional_int((orders or {}).get("order_count"))
        fill_count = self._optional_int((fills or {}).get("fill_count"))
        holding_count = self._optional_int(snapshot.get("holding_count"))
        rank_out = self._optional_int(selection.get("rank_out_of_scope_rows")) or 0
        abnormal_order_count = self._optional_int((orders or {}).get("abnormal_order_count")) or 0
        abnormal_fill_count = self._optional_int((fills or {}).get("abnormal_fill_count")) or 0
        cash_balance = self._to_decimal_value(snapshot.get("cash_balance"))
        turnover_rate = self._to_decimal_value(snapshot.get("turnover_rate"))
        max_position_weight = self._to_decimal_value(risk.get("max_position_weight"))

        checks: list[dict[str, Any]] = []
        checks.append({
            "check_name": "rank_scope",
            "status": "PASS" if rank_out == 0 else "FAIL",
            "reason": f"rank_out_of_scope_rows={rank_out}",
        })
        order_fill_match = order_count is not None and order_count == fill_count
        checks.append({
            "check_name": "order_fill_consistency",
            "status": "PASS" if order_fill_match else "WARN",
            "reason": f"order={order_count},fill={fill_count}",
        })
        holding_target_match = selected_count is not None and holding_count == selected_count
        checks.append({
            "check_name": "holding_count_vs_selected_count",
            "status": "PASS" if holding_target_match else "WARN",
            "reason": f"selected={selected_count},holding={holding_count}",
        })
        checks.append({
            "check_name": "abnormal_orders",
            "status": "PASS" if abnormal_order_count == 0 else "FAIL",
            "reason": f"abnormal_order_count={abnormal_order_count}",
        })
        checks.append({
            "check_name": "abnormal_fills",
            "status": "PASS" if abnormal_fill_count == 0 else "FAIL",
            "reason": f"abnormal_fill_count={abnormal_fill_count}",
        })
        checks.append({
            "check_name": "cash_non_negative",
            "status": "PASS" if cash_balance is None or cash_balance >= Decimal("0") else "FAIL",
            "reason": f"cash_balance={snapshot.get('cash_balance')}",
        })
        checks.append({
            "check_name": "max_single_position_weight",
            "status": "WARN" if max_position_weight is not None and max_position_weight > Decimal("0.10") else "PASS",
            "reason": f"max_position_weight={risk.get('max_position_weight')}",
        })
        checks.append({
            "check_name": "turnover_rate",
            "status": "WARN" if turnover_rate is not None and turnover_rate > Decimal("1.20") else "PASS",
            "reason": f"turnover_rate={snapshot.get('turnover_rate')}",
        })
        trade_details = section.get("trade_details") or []
        missing_price_count = sum(
            1
            for row in trade_details
            if row.get("fill_status") and row.get("fill_price") is None and row.get("estimated_price") is None
        )
        failed_trade_count = sum(
            1
            for row in trade_details
            if str(row.get("order_status") or "").upper() in {"FAILED", "REJECTED", "CANCELLED"}
            or str(row.get("fill_status") or "").upper() in {"FAILED", "REJECTED", "CANCELLED"}
        )
        checks.append({
            "check_name": "price_available",
            "status": "PASS" if missing_price_count == 0 else "FAIL",
            "reason": f"missing_price_count={missing_price_count}",
        })
        checks.append({
            "check_name": "trade_failure",
            "status": "PASS" if failed_trade_count == 0 else "FAIL",
            "reason": f"failed_trade_count={failed_trade_count}",
        })
        return checks

    @staticmethod
    def _trade_reason(row: dict[str, Any]) -> str:
        parts = ProductionDailyObservationReportBuilder._trade_reason_parts(row)
        values: list[str] = []
        for key in ("strategy_reason", "sizing_reason", "price_reason", "fill_reason"):
            value = parts.get(key)
            if value:
                values.append(str(value))
        return ";".join(values) if values else "not_available"

    @staticmethod
    def _trade_reason_parts(row: dict[str, Any]) -> dict[str, str | None]:
        raw_reasons: list[str] = []
        for key in ("target_reason_code", "signal_reason_code"):
            value = row.get(key)
            if value:
                raw_reasons.append(str(value))
        status_reason = str(row.get("target_status_reason") or "")
        if status_reason:
            raw_reasons.extend([part for part in status_reason.split(";") if part])

        strategy_reason = ProductionDailyObservationReportBuilder._dedupe_join(
            part for part in raw_reasons
            if part and not part.startswith(("M7_", "price_", "raw_target_", "cash_buffer_", "lot_size="))
        )
        sizing_reason = ProductionDailyObservationReportBuilder._dedupe_join(
            part for part in raw_reasons
            if part.startswith(("M7_", "raw_target_", "cash_buffer_", "lot_size="))
        )
        price_context = ProductionDailyObservationReportBuilder._dedupe_join(
            part for part in raw_reasons if part.startswith("price_")
        )
        if row.get("price_source"):
            price_context = ProductionDailyObservationReportBuilder._dedupe_join(
                [price_context, f"fill_price_source={row.get('price_source')}"]
            )
        fill_reason = ProductionDailyObservationReportBuilder._dedupe_join(
            [
                f"fill_rule={row.get('fill_rule')}" if row.get("fill_rule") else None,
                f"fill_status={row.get('fill_status')}" if row.get("fill_status") else None,
                f"order_status={row.get('order_status')}" if row.get("order_status") else None,
            ]
        )
        return {
            "strategy_reason": strategy_reason,
            "sizing_reason": sizing_reason,
            "price_reason": price_context,
            "fill_reason": fill_reason,
        }

    @staticmethod
    def _trade_reason_summary(parts: dict[str, Any]) -> str:
        strategy = parts.get("strategy_reason") or "strategy_reason=not_available"
        sizing = parts.get("sizing_reason") or "sizing_reason=not_available"
        fill = parts.get("fill_reason") or "fill_reason=not_available"
        return f"{strategy}; {sizing}; {fill}"

    @staticmethod
    def _dedupe_join(values: Any, separator: str = ";") -> str | None:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            if value is None:
                continue
            text_value = str(value).strip()
            if not text_value or text_value in seen:
                continue
            seen.add(text_value)
            ordered.append(text_value)
        return separator.join(ordered) if ordered else None

    @staticmethod
    def _dedupe_strings(values: Any) -> list[str]:
        """Return non-empty strings in original order with duplicates removed.

        This helper is used by production daily observation conclusion rendering,
        where callers need a list for slicing instead of the joined string returned
        by _dedupe_join().
        """
        if values is None:
            return []
        if isinstance(values, str):
            iterable = [values]
        else:
            try:
                iterable = list(values)
            except TypeError:
                iterable = [values]

        seen: set[str] = set()
        ordered: list[str] = []
        for value in iterable:
            if value is None:
                continue
            text_value = str(value).strip()
            if not text_value or text_value in seen:
                continue
            seen.add(text_value)
            ordered.append(text_value)
        return ordered

    def _resolve_next_trade_date(self, report_date: date) -> date | None:
        """Resolve the next open trading day after report_date for production observation.

        This is intentionally read-only. If the trading calendar is unavailable, the
        next-trade plan section will render a WARN instead of blocking the daily report.
        """
        next_trade_date = self._safe_scalar(
            """
            select trade_date
            from public.meta_trading_calendar
            where is_open = true
              and trade_date > :report_date
            order by trade_date asc
            limit 1
            """,
            {"report_date": report_date},
        )
        return self._to_date(next_trade_date)

    def _build_next_trade_plan(
        self,
        *,
        report_date: date,
        signal_as_of_date: date,
        next_trade_date: date | None,
        campaign_reports: list[dict[str, Any]],
        detail_limit: int,
    ) -> dict[str, Any]:
        """Build a front-page next-trading-day plan from already materialized production tables.

        The section does not invent buy/sell signals. It only shows next_trade_date
        target/order rows if they have been materialized by the production chain. When
        no next-date plan exists yet, the section is WARN and explains that absence is
        not equivalent to a zero-buy/zero-sell decision.
        """
        campaign_plans: list[dict[str, Any]] = []
        for campaign in campaign_reports:
            campaign_plans.append(
                self._build_campaign_next_trade_plan(
                    campaign=campaign,
                    report_date=report_date,
                    signal_as_of_date=signal_as_of_date,
                    next_trade_date=next_trade_date,
                    detail_limit=detail_limit,
                )
            )

        statuses = [str(item.get("status") or "WARN").upper() for item in campaign_plans]
        materialized_plans = [
            item
            for item in campaign_plans
            if item.get("plan_basis") not in {
                "no_next_trade_target_or_order_materialized",
                "next_trade_date_unresolved",
                "missing_portfolio_id",
                "query_failed",
                "not_checked",
            }
        ]
        query_failed = any(item.get("plan_basis") == "query_failed" for item in campaign_plans)
        if not campaign_plans:
            status = "WARN"
            reason = "no_active_production_campaign"
        elif any(item.get("next_trade_date") is None for item in campaign_plans):
            status = "WARN"
            reason = "next_trade_date_unresolved"
        elif query_failed:
            status = "WARN"
            reason = "next_trade_plan_query_failed"
        elif materialized_plans:
            if any(value == "FAIL" for value in statuses):
                status = "FAIL"
            elif any(value == "WARN" for value in statuses):
                status = "WARN"
            else:
                status = "PASS"
            reason = "next_trade_plan_materialized"
        else:
            status = "WARN"
            reason = "no_next_trade_target_or_order_materialized"

        plan_basis_candidates = self._dedupe_strings(item.get("plan_basis") for item in campaign_plans)
        non_materialized_bases = {
            "no_next_trade_target_or_order_materialized",
            "next_trade_date_unresolved",
            "missing_portfolio_id",
            "query_failed",
            "not_checked",
        }
        top_plan_basis = next(
            (basis for basis in plan_basis_candidates if basis not in non_materialized_bases),
            reason,
        )

        return {
            "scope": "production_next_trade_plan_observation_not_independent_buy_sell_engine",
            "report_date": report_date,
            "signal_as_of_date": signal_as_of_date,
            "next_trade_date": next_trade_date,
            "status": status,
            "reason": reason,
            "plan_basis": top_plan_basis,
            "note": (
                "本节只展示已落表的 next_trade_date target/order。"
                "若 plan_basis=no_next_trade_target_or_order_materialized，表示当前日报生成时尚未观察到次日计划落表，"
                "不能解释为正式零买入/零卖出信号。"
            ),
            "campaigns": campaign_plans,
        }

    def _build_campaign_next_trade_plan(
        self,
        *,
        campaign: dict[str, Any],
        report_date: date,
        signal_as_of_date: date,
        next_trade_date: date | None,
        detail_limit: int,
    ) -> dict[str, Any]:
        portfolio_id = self._optional_int(campaign.get("portfolio_id"))
        snapshot = campaign.get("snapshot") or {}
        current_position_run_id = self._optional_int(snapshot.get("position_run_id") or snapshot.get("snapshot_run_id"))
        plan: dict[str, Any] = {
            "campaign_code": campaign.get("campaign_code"),
            "portfolio_id": portfolio_id,
            "strategy_code": campaign.get("strategy_code"),
            "strategy_version_code": campaign.get("strategy_version_code"),
            "report_date": report_date,
            "signal_as_of_date": signal_as_of_date,
            "next_trade_date": next_trade_date,
            "current_position_run_id": current_position_run_id,
            "status": "WARN",
            "reason": None,
            "plan_basis": "not_checked",
            "target_run_id": None,
            "order_run_id": None,
            "planned_buy_count": 0,
            "planned_sell_count": 0,
            "planned_hold_count": 0,
            "planned_review_count": 0,
            "planned_buy_rows": [],
            "planned_sell_rows": [],
            "planned_hold_rows": [],
            "current_position_review_rows": [],
        }
        if portfolio_id is None:
            plan["reason"] = "missing_portfolio_id"
            plan["plan_basis"] = "missing_portfolio_id"
            return plan
        if next_trade_date is None:
            plan["reason"] = "next_trade_date_unresolved"
            plan["plan_basis"] = "next_trade_date_unresolved"
            return plan

        try:
            target_rows = self._next_trade_target_rows(
                portfolio_id=portfolio_id,
                next_trade_date=next_trade_date,
                current_position_run_id=current_position_run_id,
                limit=detail_limit,
            )
            order_rows = self._next_trade_order_rows(
                portfolio_id=portfolio_id,
                next_trade_date=next_trade_date,
                limit=detail_limit,
            )
            missing_target_rows = self._next_trade_missing_from_target_rows(
                portfolio_id=portfolio_id,
                next_trade_date=next_trade_date,
                current_position_run_id=current_position_run_id,
                limit=detail_limit,
            )
        except Exception as exc:
            self._rollback_session_safely()
            plan["status"] = "WARN"
            plan["reason"] = f"query_failed:{type(exc).__name__}:{exc}"
            plan["plan_basis"] = "query_failed"
            return plan

        if target_rows:
            plan["target_run_id"] = target_rows[0].get("target_run_id")
        if order_rows:
            plan["order_run_id"] = order_rows[0].get("order_run_id")

        if order_rows:
            buy_rows = [row for row in order_rows if str(row.get("order_side") or "").upper() == "BUY"]
            sell_rows = [row for row in order_rows if str(row.get("order_side") or "").upper() == "SELL"]
            hold_rows = [row for row in target_rows if str(row.get("plan_action") or "").upper() == "HOLD_TARGET"]
            plan["plan_basis"] = "next_trade_date_order_plan_materialized"
            plan["status"] = "PASS"
            plan["reason"] = "next_trade_order_rows_observed"
        elif target_rows:
            buy_rows = [
                row for row in target_rows
                if str(row.get("plan_action") or "").upper() in {"BUY_NEW_TARGET", "BUY_INCREASE_TARGET"}
            ]
            sell_rows = [
                row for row in target_rows
                if str(row.get("plan_action") or "").upper() == "SELL_REDUCE_TARGET"
            ]
            sell_rows.extend(missing_target_rows)
            hold_rows = [row for row in target_rows if str(row.get("plan_action") or "").upper() == "HOLD_TARGET"]
            plan["plan_basis"] = "next_trade_date_target_plan_materialized_without_order"
            plan["status"] = "PASS"
            plan["reason"] = "next_trade_target_rows_observed_without_order_rows"
        else:
            buy_rows = []
            sell_rows = []
            hold_rows = []
            plan["current_position_review_rows"] = (campaign.get("positions_preview") or [])[: min(detail_limit, 15)]
            plan["plan_basis"] = "no_next_trade_target_or_order_materialized"
            plan["status"] = "WARN"
            plan["reason"] = "当前日报生成时未观察到 next_trade_date 的 target/order；不能解释为正式零买入/零卖出。"

        plan["planned_buy_rows"] = buy_rows[:detail_limit]
        plan["planned_sell_rows"] = sell_rows[:detail_limit]
        plan["planned_hold_rows"] = hold_rows[: min(detail_limit, 30)]
        plan["planned_buy_count"] = len(buy_rows)
        plan["planned_sell_count"] = len(sell_rows)
        plan["planned_hold_count"] = len(hold_rows)
        plan["planned_review_count"] = len(plan.get("current_position_review_rows") or [])
        return plan

    def _next_trade_target_rows(
        self,
        *,
        portfolio_id: int,
        next_trade_date: date,
        current_position_run_id: int | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        sql = """
        with target_run as (
            select max(run_id) as target_run_id
            from public.trading_paper_target_position
            where portfolio_id = :portfolio_id
              and effective_date = :next_trade_date
        ),
        current_pos as (
            select
                instrument_id,
                quantity as current_quantity,
                market_value as current_market_value,
                total_pnl as current_total_pnl,
                position_status as current_position_status
            from public.trading_paper_position
            where portfolio_id = :portfolio_id
              and run_id = :current_position_run_id
        )
        select
            t.run_id as target_run_id,
            t.effective_date,
            t.instrument_id,
            mi.instrument_code,
            mi.symbol,
            mi.display_name,
            t.rank_no,
            t.score,
            t.target_weight,
            t.target_quantity,
            t.reason_code as target_reason_code,
            t.status_reason as target_status_reason,
            ss.rank_in_batch as source_rank,
            ss.reason_code as signal_reason_code,
            cp.current_quantity,
            cp.current_market_value,
            cp.current_total_pnl,
            cp.current_position_status,
            case
                when cp.instrument_id is null or coalesce(cp.current_quantity, 0) = 0 then 'BUY_NEW_TARGET'
                when coalesce(t.target_quantity, 0) > coalesce(cp.current_quantity, 0) then 'BUY_INCREASE_TARGET'
                when coalesce(t.target_quantity, 0) < coalesce(cp.current_quantity, 0) then 'SELL_REDUCE_TARGET'
                else 'HOLD_TARGET'
            end as plan_action,
            'target_quantity_vs_current_position' as plan_reason
        from public.trading_paper_target_position t
        join target_run tr on tr.target_run_id = t.run_id
        left join current_pos cp on cp.instrument_id = t.instrument_id
        left join public.strategy_signal ss on ss.id = t.strategy_signal_id
        left join public.meta_instrument mi on mi.id = t.instrument_id
        where t.portfolio_id = :portfolio_id
          and t.effective_date = :next_trade_date
        order by t.rank_no nulls last, t.score desc nulls last, t.instrument_id
        limit :limit
        """
        return self._rows(
            sql,
            {
                "portfolio_id": portfolio_id,
                "next_trade_date": next_trade_date,
                "current_position_run_id": current_position_run_id,
                "limit": limit,
            },
        )

    def _next_trade_order_rows(
        self,
        *,
        portfolio_id: int,
        next_trade_date: date,
        limit: int,
    ) -> list[dict[str, Any]]:
        sql = """
        with order_run as (
            select max(run_id) as order_run_id
            from public.trading_paper_order
            where portfolio_id = :portfolio_id
              and effective_date = :next_trade_date
        )
        select
            o.run_id as order_run_id,
            o.effective_date,
            o.instrument_id,
            mi.instrument_code,
            mi.symbol,
            mi.display_name,
            o.order_side,
            o.order_type,
            o.price_fill_rule,
            o.target_quantity,
            o.order_quantity,
            o.estimated_price,
            o.estimated_gross_amount,
            o.estimated_fee,
            o.estimated_net_amount,
            o.status as order_status,
            o.reject_reason,
            t.run_id as target_run_id,
            t.rank_no,
            t.score,
            t.target_weight,
            t.reason_code as target_reason_code,
            t.status_reason as target_status_reason,
            ss.rank_in_batch as source_rank,
            ss.reason_code as signal_reason_code,
            upper(o.order_side) as plan_action,
            'next_trade_date_order' as plan_reason
        from public.trading_paper_order o
        join order_run r on r.order_run_id = o.run_id
        left join public.trading_paper_target_position t on t.id = o.target_position_id
        left join public.strategy_signal ss on ss.id = t.strategy_signal_id
        left join public.meta_instrument mi on mi.id = o.instrument_id
        where o.portfolio_id = :portfolio_id
          and o.effective_date = :next_trade_date
        order by case when upper(o.order_side) = 'SELL' then 0 else 1 end, t.rank_no nulls last, o.id
        limit :limit
        """
        return self._rows(
            sql,
            {
                "portfolio_id": portfolio_id,
                "next_trade_date": next_trade_date,
                "limit": limit,
            },
        )

    def _next_trade_missing_from_target_rows(
        self,
        *,
        portfolio_id: int,
        next_trade_date: date,
        current_position_run_id: int | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        if current_position_run_id is None:
            return []
        sql = """
        with target_run as (
            select max(run_id) as target_run_id
            from public.trading_paper_target_position
            where portfolio_id = :portfolio_id
              and effective_date = :next_trade_date
        ),
        target_instruments as (
            select instrument_id
            from public.trading_paper_target_position t
            join target_run tr on tr.target_run_id = t.run_id
            where t.portfolio_id = :portfolio_id
              and t.effective_date = :next_trade_date
        )
        select
            null::bigint as target_run_id,
            :next_trade_date as effective_date,
            p.instrument_id,
            mi.instrument_code,
            mi.symbol,
            mi.display_name,
            null::integer as rank_no,
            null::numeric as score,
            null::numeric as target_weight,
            0::numeric as target_quantity,
            null::text as target_reason_code,
            null::text as target_status_reason,
            null::integer as source_rank,
            null::text as signal_reason_code,
            p.quantity as current_quantity,
            p.market_value as current_market_value,
            p.total_pnl as current_total_pnl,
            p.position_status as current_position_status,
            'SELL_CANDIDATE_NOT_IN_NEXT_TARGET' as plan_action,
            'current_open_position_missing_from_next_target' as plan_reason
        from public.trading_paper_position p
        left join public.meta_instrument mi on mi.id = p.instrument_id
        where p.portfolio_id = :portfolio_id
          and p.run_id = :current_position_run_id
          and upper(coalesce(p.position_status, '')) = 'OPEN'
          and coalesce(p.quantity, 0) > 0
          and not exists (
              select 1
              from target_instruments ti
              where ti.instrument_id = p.instrument_id
          )
        order by p.market_value desc nulls last, p.instrument_id
        limit :limit
        """
        return self._rows(
            sql,
            {
                "portfolio_id": portfolio_id,
                "next_trade_date": next_trade_date,
                "current_position_run_id": current_position_run_id,
                "limit": limit,
            },
        )

    def _build_used_date_guard(
        self,
        *,
        report_date: date,
        signal_as_of_date: date,
        waterline: list[dict[str, Any]],
        campaign_reports: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Describe which dates are available vs. actually used by the production report."""
        max_dates = [
            self._to_date(row.get("max_date"))
            for row in waterline
            if row.get("max_date") is not None
            and row.get("freshness_basis") != "reference_data"
            and row.get("table_name") != "meta_trading_calendar"
        ]
        latest_available_date = max((d for d in max_dates if d is not None), default=None)
        details: list[dict[str, Any]] = []
        status = "PASS"
        reasons: list[str] = []

        def add_detail(name: str, used_date: Any, expected_max: Any, detail_status: str, reason: str) -> None:
            nonlocal status
            details.append({
                "check_name": name,
                "used_date": self._to_date(used_date),
                "expected_max_date": self._to_date(expected_max),
                "status": detail_status,
                "reason": reason,
            })
            if detail_status == "FAIL":
                status = "FAIL"
            elif detail_status == "WARN" and status != "FAIL":
                status = "WARN"

        if signal_as_of_date > report_date:
            add_detail("signal_as_of_date_not_future", signal_as_of_date, report_date, "FAIL", "signal_as_of_date_after_report_date")
            reasons.append("signal_as_of_date_after_report_date")
        else:
            add_detail("signal_as_of_date_not_future", signal_as_of_date, report_date, "PASS", "signal_as_of_date<=report_date")

        for campaign in campaign_reports:
            campaign_code = str(campaign.get("campaign_code") or "")
            selection = campaign.get("selection_summary") or {}
            source_signal_run_id = selection.get("source_signal_run_id")
            if source_signal_run_id is not None:
                signal_max_date = self._safe_scalar(
                    "select max(as_of_date) from public.strategy_signal where run_id = :run_id",
                    {"run_id": source_signal_run_id},
                )
                signal_max_date = self._to_date(signal_max_date)
                if signal_max_date is None:
                    add_detail(f"{campaign_code}:source_signal_run_date", None, signal_as_of_date, "WARN", f"source_signal_run_id={source_signal_run_id};no_signal_date")
                elif signal_max_date > signal_as_of_date:
                    add_detail(f"{campaign_code}:source_signal_run_date", signal_max_date, signal_as_of_date, "FAIL", f"source_signal_run_id={source_signal_run_id};source_signal_after_signal_as_of_date")
                    reasons.append(f"{campaign_code}:source_signal_after_signal_as_of_date")
                else:
                    add_detail(f"{campaign_code}:source_signal_run_date", signal_max_date, signal_as_of_date, "PASS", f"source_signal_run_id={source_signal_run_id};source_signal_date<=signal_as_of_date")

            target_date = self._to_date(selection.get("effective_date"))
            if target_date is not None:
                add_detail(
                    f"{campaign_code}:target_effective_date",
                    target_date,
                    report_date,
                    "PASS" if target_date <= report_date else "FAIL",
                    "target_effective_date<=report_date" if target_date <= report_date else "target_effective_date_after_report_date",
                )

            trade = campaign.get("trade_summary") or {}
            orders = trade.get("orders") or {}
            fills = trade.get("fills") or {}
            snapshot = campaign.get("snapshot") or {}
            for name, used_date in [
                ("order_effective_date", self._to_date(orders.get("effective_date"))),
                ("fill_date", self._to_date(fills.get("fill_date"))),
                ("snapshot_date", self._to_date(snapshot.get("snapshot_date"))),
            ]:
                if used_date is None:
                    continue
                add_detail(
                    f"{campaign_code}:{name}",
                    used_date,
                    report_date,
                    "PASS" if used_date <= report_date else "FAIL",
                    f"{name}<=report_date" if used_date <= report_date else f"{name}_after_report_date",
                )

        if not reasons:
            reasons.append("used_signal_date_is_t_minus_1_or_earlier_and_trade_dates_do_not_exceed_report_date")

        return {
            "latest_available_date": latest_available_date,
            "used_for_signal_date": signal_as_of_date,
            "used_for_trade_date": report_date,
            "future_data_guard_status": status,
            "future_data_guard_reason": ";".join(reasons),
            "details": details,
        }

    @classmethod
    def _build_daily_conclusion_summary(cls, payload: dict[str, Any]) -> list[dict[str, Any]]:
        waterline = payload.get("waterline") or []
        market_context = payload.get("market_context") or {}
        breadth = market_context.get("breadth") or {}
        campaigns = payload.get("campaigns") or []
        first_campaign = campaigns[0] if campaigns else {}
        runtime = first_campaign.get("runtime_observation") or {}
        selection = first_campaign.get("selection_summary") or {}
        trade = first_campaign.get("trade_summary") or {}
        orders = trade.get("orders") or {}
        fills = trade.get("fills") or {}
        snapshot = first_campaign.get("snapshot") or {}
        risk = first_campaign.get("risk_metrics") or {}
        used_guard = payload.get("used_date_guard") or {}
        market_alignment = market_context.get("strategy_alignment") or []
        first_alignment = market_alignment[0] if market_alignment else {}

        failed = [row for row in waterline if row.get("status") == "FAIL"]
        warns = [row for row in waterline if row.get("status") == "WARN"]
        if failed:
            data_status = "FAIL"
            data_summary = "关键数据水位存在 FAIL：" + ", ".join(str(x.get("table_name")) for x in failed[:5])
        elif warns:
            data_status = "WARN"
            data_summary = "存在非关键数据水位 WARN：" + ", ".join(str(x.get("table_name")) for x in warns[:5])
        else:
            data_status = "PASS"
            data_summary = "关键数据水位满足本次生产观察要求。"

        market_state = breadth.get("market_breadth_state") or "UNKNOWN"
        market_summary = (
            f"{market_state}; 上涨比例 {cls._fmt_percent(breadth.get('up_ratio'), 2)}，"
            f"下跌比例 {cls._fmt_percent(breadth.get('down_ratio'), 2)}，"
            f"涨停 {breadth.get('limit_up_rows')}，跌停 {breadth.get('limit_down_rows')}。"
        )

        buy_count = cls._optional_int((orders or {}).get("buy_order_count")) or 0
        sell_count = cls._optional_int((orders or {}).get("sell_order_count")) or 0
        fill_count = cls._optional_int((fills or {}).get("fill_count")) or 0
        action_summary = (
            f"{runtime.get('runtime_action') or 'UNKNOWN'}; "
            f"selected={selection.get('selected_count')}, buy={buy_count}, sell={sell_count}, fill={fill_count}."
        )

        cash_ratio_value: Any = risk.get("cash_ratio")
        if cash_ratio_value in (None, ""):
            cash_ratio_value = cls._safe_ratio(snapshot.get("cash_balance"), snapshot.get("total_equity"))
        stock_exposure_value: Any = risk.get("stock_exposure")
        if stock_exposure_value in (None, ""):
            cash_ratio_decimal = cls._to_decimal_value(cash_ratio_value)
            if cash_ratio_decimal is not None:
                stock_exposure_value = Decimal("1") - cash_ratio_decimal

        daily_return_text = cls._fmt_percent(snapshot.get("daily_return"), 4) or "UNKNOWN"
        daily_pnl_text = cls._fmt_money(snapshot.get("daily_pnl")) or "UNKNOWN"
        cash_ratio_text = cls._fmt_percent(cash_ratio_value, 2) or "UNKNOWN"
        stock_exposure_text = cls._fmt_percent(stock_exposure_value, 2) or "UNKNOWN"
        portfolio_summary = (
            f"daily_return={daily_return_text}, "
            f"daily_pnl={daily_pnl_text}, "
            f"cash_ratio={cash_ratio_text}, "
            f"stock_exposure={stock_exposure_text}."
        )

        risk_items: list[str] = []
        if str(market_state) == "BREADTH_WEAK":
            risk_items.append("市场宽度偏弱")
        stock_exposure = cls._to_decimal_value(stock_exposure_value)
        if stock_exposure is not None and stock_exposure >= Decimal("0.95"):
            risk_items.append(f"股票仓位较高 {cls._fmt_percent(stock_exposure, 2)}")
        if str(used_guard.get("future_data_guard_status")) != "PASS":
            risk_items.append(f"future_data_guard={used_guard.get('future_data_guard_status')}")
        if payload.get("git_commit_status") == "WARN":
            risk_items.append("git_commit 未解析到真实提交号")
        risk_summary = "；".join(risk_items) if risk_items else "未发现需要置顶的生产观察风险。"

        focus_items: list[str] = []
        top_mainline = first_alignment.get("top_mainline_tag")
        if top_mainline:
            focus_items.append(f"观察主线暴露 {top_mainline} 是否延续")
        for note in (market_context.get("summary") or [])[:3]:
            if "strong_concept" in str(note) or "strong_industry" in str(note):
                focus_items.append(str(note))
        if not focus_items:
            focus_items.append("观察市场宽度、主线强弱和组合暴露变化")
        focus_summary = "；".join(cls._dedupe_strings(focus_items)[:4])

        return [
            {"item": "今日生产状态", "status": payload.get("overall_status"), "summary": "production_daily_observation_report 已生成。"},
            {"item": "数据状态", "status": data_status, "summary": data_summary},
            {"item": "数据使用语义", "status": used_guard.get("future_data_guard_status"), "summary": f"signal_date={cls._json_default(used_guard.get('used_for_signal_date'))}; trade_date={cls._json_default(used_guard.get('used_for_trade_date'))}; {used_guard.get('future_data_guard_reason')}"},
            {"item": "市场状态", "status": market_context.get("status"), "summary": market_summary},
            {"item": "策略动作", "status": first_campaign.get("status"), "summary": action_summary},
            {"item": "组合表现", "status": first_campaign.get("status"), "summary": portfolio_summary},
            {"item": "主要风险", "status": "WARN" if risk_items else "PASS", "summary": risk_summary},
            {"item": "次日观察重点", "status": "INFO", "summary": focus_summary},
        ]

    @classmethod
    def _build_next_trade_plan_sla(cls, payload: dict[str, Any]) -> dict[str, Any]:
        next_trade_plan = payload.get("next_trade_plan") or {}
        reason = str(next_trade_plan.get("reason") or "missing_next_trade_plan")
        plan_basis = str(next_trade_plan.get("plan_basis") or reason)
        materialized_bases = {
            "next_trade_date_order_plan_materialized",
            "next_trade_date_target_plan_materialized_without_order",
        }
        if plan_basis in materialized_bases or reason == "next_trade_plan_materialized":
            status = "PASS"
            blocker = "next_trade_date_plan_materialized"
        elif (
            plan_basis == "query_failed"
            or reason == "next_trade_plan_query_failed"
            or plan_basis.startswith("query_failed:")
            or reason.startswith("query_failed:")
        ):
            status = "FAIL"
            blocker = "next_trade_plan_query_failed"
        else:
            status = "WARN"
            blocker = plan_basis or reason

        materialized_at = None
        for campaign in next_trade_plan.get("campaigns") or []:
            if campaign.get("target_run_id") or campaign.get("order_run_id"):
                materialized_at = cls._json_default(payload.get("generated_at"))
                break

        return {
            "status": status,
            "reason": reason,
            "plan_basis": plan_basis,
            "next_trade_date": next_trade_plan.get("next_trade_date") or payload.get("next_trade_date"),
            "expected_time": "daily runtime 18:30 后；若 next_trade_date 计划生成链路已接入，应在生产日报前完成 target/order 落表。",
            "materialized_at": materialized_at,
            "blocker": blocker,
            "next_check_command": "docker exec stock-quant-scheduler bash -lc 'cd /app && grep -nE \"0.3 次日交易计划|plan_basis|Next Trade Plan SLA\" artifacts/production/daily_observation/latest/production_daily_observation_latest.md'",
            "note": "本 SLA 仅观察 next_trade_date target/order 是否已落表，不生成或硬造买卖点。",
        }

    @classmethod
    def _build_buy_price_quality(cls, payload: dict[str, Any]) -> dict[str, Any]:
        """Observe NEXT_OPEN buy price quality from existing order/fill rows.

        This is an operational observation only. It compares the order estimated
        price (currently derived from the signal-side close in the existing
        execution chain) with the actual simulated fill price (NEXT_OPEN). It
        does not introduce a new buy-point engine or change execution behavior.
        """
        campaign_rows: list[dict[str, Any]] = []
        for campaign in payload.get("campaigns") or []:
            buy_rows = [
                row for row in (campaign.get("trade_details") or [])
                if str(row.get("order_side") or "").upper() == "BUY"
            ]
            quality_rows: list[dict[str, Any]] = []
            total_gap_cost = Decimal("0")
            total_estimated_amount = Decimal("0")
            gap_ratio_sum = Decimal("0")
            computed_count = 0
            favorable_count = 0
            unfavorable_count = 0
            flat_count = 0

            for row in buy_rows:
                estimated_price = cls._to_decimal_value(row.get("estimated_price"))
                fill_price = cls._to_decimal_value(row.get("fill_price"))
                quantity = cls._to_decimal_value(row.get("fill_quantity") or row.get("order_quantity") or row.get("target_quantity"))
                if estimated_price is None or fill_price is None or estimated_price == 0 or quantity is None:
                    continue
                gap_amount = fill_price - estimated_price
                gap_ratio = gap_amount / estimated_price
                estimated_gap_cost = gap_amount * quantity
                estimated_amount = estimated_price * quantity
                total_gap_cost += estimated_gap_cost
                total_estimated_amount += estimated_amount
                gap_ratio_sum += gap_ratio
                computed_count += 1
                if gap_ratio > 0:
                    unfavorable_count += 1
                elif gap_ratio < 0:
                    favorable_count += 1
                else:
                    flat_count += 1
                quality_row = {
                    "campaign_code": campaign.get("campaign_code"),
                    "rank_no": row.get("rank_no"),
                    "instrument_id": row.get("instrument_id"),
                    "instrument_code": row.get("instrument_code"),
                    "symbol": row.get("symbol"),
                    "display_name": row.get("display_name"),
                    "estimated_price": estimated_price,
                    "fill_price": fill_price,
                    "quantity": quantity,
                    "gap_amount": gap_amount,
                    "gap_ratio": gap_ratio,
                    "estimated_gap_cost": estimated_gap_cost,
                    "order_status": row.get("order_status"),
                    "fill_status": row.get("fill_status"),
                    "entry_policy": row.get("entry_policy"),
                    "price_source": row.get("price_source"),
                    "fill_rule": row.get("fill_rule"),
                }
                quality_rows.append(quality_row)

            avg_gap_ratio = (gap_ratio_sum / Decimal(computed_count)) if computed_count else None
            weighted_gap_ratio = cls._safe_ratio(total_gap_cost, total_estimated_amount) if computed_count else None
            warning_reasons: list[str] = []
            if not buy_rows:
                status = "WARN"
                reason = "no_buy_order_rows"
            elif computed_count == 0:
                status = "WARN"
                reason = "no_buy_rows_with_estimated_and_fill_price"
            else:
                if (avg_gap_ratio is not None and avg_gap_ratio > Decimal("0.005")) or (
                    weighted_gap_ratio is not None and weighted_gap_ratio > Decimal("0.005")
                ):
                    warning_reasons.append("avg_or_weighted_unfavorable_gap_gt_0_5pct")
                if unfavorable_count > favorable_count and total_gap_cost > 0:
                    warning_reasons.append("unfavorable_gap_count_gt_favorable")
                status = "WARN" if warning_reasons else "PASS"
                reason = ";".join(warning_reasons) if warning_reasons else "buy_price_quality_observable"

            worst_rows = sorted(
                quality_rows,
                key=lambda item: cls._to_decimal_value(item.get("gap_ratio")) or Decimal("-999"),
                reverse=True,
            )[:5]
            best_rows = sorted(
                quality_rows,
                key=lambda item: cls._to_decimal_value(item.get("gap_ratio")) or Decimal("999"),
            )[:5]
            campaign_rows.append({
                "campaign_code": campaign.get("campaign_code"),
                "portfolio_id": campaign.get("portfolio_id"),
                "status": status,
                "reason": reason,
                "scope": "production_observation_next_open_price_quality_not_buy_point_engine",
                "buy_order_count": len(buy_rows),
                "computed_count": computed_count,
                "favorable_gap_count": favorable_count,
                "unfavorable_gap_count": unfavorable_count,
                "flat_gap_count": flat_count,
                "avg_gap_ratio": avg_gap_ratio,
                "weighted_gap_ratio": weighted_gap_ratio,
                "estimated_gap_cost": total_gap_cost if computed_count else None,
                "estimated_signal_amount": total_estimated_amount if computed_count else None,
                "worst_gap_top": worst_rows,
                "best_gap_top": best_rows,
            })

        statuses = [row.get("status") for row in campaign_rows]
        status = "FAIL" if "FAIL" in statuses else ("WARN" if "WARN" in statuses else "PASS")
        if not campaign_rows:
            status = "WARN"
            reason = "no_campaigns_for_buy_price_quality"
        else:
            reason = f"campaign_count={len(campaign_rows)},warn={statuses.count('WARN')}"
        return {
            "status": status,
            "reason": reason,
            "scope": "production_observation_price_gap_from_estimated_signal_price_to_next_open_fill",
            "campaigns": campaign_rows,
        }

    def _build_daily_diff(
        self,
        *,
        project_root: Path,
        output_root: Path,
        report_date: date,
        current_payload: dict[str, Any],
    ) -> dict[str, Any]:
        previous_payload, previous_path, previous_lookup_reason = self._load_previous_report_payload(
            output_root=output_root,
            report_date=report_date,
        )
        if previous_payload is None:
            return {
                "status": "WARN",
                "reason": previous_lookup_reason,
                "previous_report_date": None,
                "previous_report_path": str(previous_path) if previous_path else None,
                "expected_previous_report_date": self._resolve_signal_as_of_date(report_date),
                "scope": "production_daily_diff_observation",
                "rows": [],
                "summary": [],
            }

        rows: list[dict[str, Any]] = []
        summary: list[str] = []

        def add_metric(metric: str, current: Any, previous: Any, delta: Any = None, status: str = "PASS", reason: str = "") -> None:
            rows.append({
                "metric": metric,
                "current_value": current,
                "previous_value": previous,
                "delta": delta,
                "status": status,
                "reason": reason,
            })

        def _missing_observation_status(metric_name: str, current: Any, previous: Any, default_reason: str) -> tuple[str, str]:
            current_missing = current in (None, "")
            previous_missing = previous in (None, "")
            if current_missing and previous_missing:
                return "WARN", f"{metric_name}_missing_in_current_and_previous"
            if current_missing:
                return "WARN", f"{metric_name}_missing_in_current"
            if previous_missing:
                return "WARN", f"{metric_name}_missing_in_previous"
            return "PASS", default_reason

        previous_report_date = self._to_date(previous_payload.get("report_date")) or previous_payload.get("report_date")
        expected_previous_report_date = self._resolve_signal_as_of_date(report_date)
        previous_date_status = "PASS"
        previous_date_reason = "previous_report_date_matches_expected_previous_trade_date"
        if previous_report_date is None:
            previous_date_status = "WARN"
            previous_date_reason = "previous_report_date_missing"
        elif expected_previous_report_date is not None and previous_report_date != expected_previous_report_date:
            previous_date_status = "WARN"
            previous_date_reason = f"previous_report_date_not_expected_previous_trade_date:{self._json_default(previous_report_date)}!={self._json_default(expected_previous_report_date)}"
        add_metric(
            "previous_report_freshness",
            report_date,
            previous_report_date,
            None,
            previous_date_status,
            previous_date_reason,
        )

        current_status = current_payload.get("overall_status")
        previous_status = previous_payload.get("overall_status")
        add_metric(
            "overall_status",
            current_status,
            previous_status,
            None,
            "WARN" if current_status != previous_status else "PASS",
            "overall_status_changed" if current_status != previous_status else "overall_status_unchanged",
        )

        current_feature = current_payload.get("feature_readiness") or {}
        previous_feature = previous_payload.get("feature_readiness") or {}
        for metric_name, key in (
            ("feature_valid_instrument_count", "valid_instrument_count"),
            ("feature_universe_size", "universe_size"),
            ("feature_excluded_instrument_count", "excluded_instrument_count"),
            ("feature_missing_feature_count", "missing_feature_count"),
        ):
            current_value = self._optional_int(current_feature.get(key))
            previous_value = self._optional_int(previous_feature.get(key))
            delta_value = (current_value - previous_value) if current_value is not None and previous_value is not None else None
            metric_status, metric_reason = _missing_observation_status(metric_name, current_value, previous_value, "delta_observed")
            if metric_status == "PASS" and metric_name == "feature_valid_instrument_count" and delta_value is not None and delta_value <= -500:
                metric_status = "WARN"
                metric_reason = "feature_valid_count_drop_ge_500"
            add_metric(metric_name, current_value, previous_value, delta_value, metric_status, metric_reason)

        current_campaign = self._first_campaign_payload(current_payload)
        previous_campaign = self._first_campaign_payload(previous_payload)
        current_snapshot = current_campaign.get("snapshot") or {}
        previous_snapshot = previous_campaign.get("snapshot") or {}
        current_risk = current_campaign.get("risk_metrics") or {}
        previous_risk = previous_campaign.get("risk_metrics") or {}

        for metric_name, getter in (
            ("daily_return", lambda p, c, r, s: s.get("daily_return")),
            ("daily_pnl", lambda p, c, r, s: s.get("daily_pnl")),
            ("total_equity", lambda p, c, r, s: s.get("total_equity")),
            ("cash_ratio", lambda p, c, r, s: r.get("cash_ratio") if r.get("cash_ratio") not in (None, "") else self._safe_ratio(s.get("cash_balance"), s.get("total_equity"))),
            ("stock_exposure", lambda p, c, r, s: r.get("stock_exposure") if r.get("stock_exposure") not in (None, "") else self._derive_stock_exposure_from_snapshot(s)),
        ):
            current_value = getter(current_payload, current_campaign, current_risk, current_snapshot)
            previous_value = getter(previous_payload, previous_campaign, previous_risk, previous_snapshot)
            current_dec = self._to_decimal_value(current_value)
            previous_dec = self._to_decimal_value(previous_value)
            delta_value = (current_dec - previous_dec) if current_dec is not None and previous_dec is not None else None
            metric_status, metric_reason = _missing_observation_status(metric_name, current_value, previous_value, "delta_observed")
            if metric_status == "PASS" and metric_name == "stock_exposure" and delta_value is not None and abs(delta_value) >= Decimal("0.20"):
                metric_status = "WARN"
                metric_reason = "stock_exposure_abs_change_ge_20pct"
            add_metric(metric_name, current_value, previous_value, delta_value, metric_status, metric_reason)

        current_selected = self._instrument_code_set(current_campaign.get("selected_instruments") or [])
        previous_selected = self._instrument_code_set(previous_campaign.get("selected_instruments") or [])
        selected_overlap = current_selected & previous_selected
        selected_overlap_ratio = self._safe_ratio(len(selected_overlap), len(previous_selected)) if previous_selected else None
        if not current_selected or not previous_selected:
            selected_status = "WARN"
            selected_reason = "selected_overlap_not_available"
        elif selected_overlap_ratio is not None and selected_overlap_ratio < Decimal("0.50"):
            selected_status = "WARN"
            selected_reason = f"overlap_ratio={self._fmt_percent(selected_overlap_ratio, 2)}"
        else:
            selected_status = "PASS"
            selected_reason = f"overlap_ratio={self._fmt_percent(selected_overlap_ratio, 2) if selected_overlap_ratio is not None else 'UNKNOWN'}"
        add_metric(
            "selected_overlap_with_previous_day",
            len(current_selected),
            len(previous_selected),
            len(selected_overlap),
            selected_status,
            selected_reason,
        )

        current_holding = self._instrument_code_set(current_campaign.get("positions_preview") or [])
        previous_holding = self._instrument_code_set(previous_campaign.get("positions_preview") or [])
        holding_overlap = current_holding & previous_holding
        holding_overlap_ratio = self._safe_ratio(len(holding_overlap), len(previous_holding)) if previous_holding else None
        if not current_holding or not previous_holding:
            holding_status = "WARN"
            holding_reason = "holding_overlap_not_available"
        elif holding_overlap_ratio is not None and holding_overlap_ratio < Decimal("0.50"):
            holding_status = "WARN"
            holding_reason = f"overlap_ratio={self._fmt_percent(holding_overlap_ratio, 2)}"
        else:
            holding_status = "PASS"
            holding_reason = f"overlap_ratio={self._fmt_percent(holding_overlap_ratio, 2) if holding_overlap_ratio is not None else 'UNKNOWN'}"
        add_metric(
            "holding_overlap_with_previous_day",
            len(current_holding),
            len(previous_holding),
            len(holding_overlap),
            holding_status,
            holding_reason,
        )

        current_mainline = self._top_mainline_summary(current_payload)
        previous_mainline = self._top_mainline_summary(previous_payload)
        mainline_changed = current_mainline.get("tag") != previous_mainline.get("tag")
        if not current_mainline.get("tag") or not previous_mainline.get("tag"):
            mainline_status = "WARN"
            mainline_reason = f"current_match={current_mainline.get('match')};previous_match={previous_mainline.get('match')};top_mainline_not_available"
        else:
            mainline_status = "WARN" if mainline_changed else "PASS"
            mainline_reason = (
                f"current_match={current_mainline.get('match')};previous_match={previous_mainline.get('match')};"
                + ("top_mainline_changed" if mainline_changed else "top_mainline_unchanged")
            )
        add_metric(
            "top_mainline_tag",
            current_mainline.get("tag"),
            previous_mainline.get("tag"),
            None,
            mainline_status,
            mainline_reason,
        )

        current_runtime = (current_campaign.get("runtime_observation") or {}).get("runtime_action")
        previous_runtime = (previous_campaign.get("runtime_observation") or {}).get("runtime_action")
        runtime_status = "WARN" if current_runtime != previous_runtime else "PASS"
        runtime_reason = "runtime_action_changed" if current_runtime != previous_runtime else "runtime_action_unchanged"
        if current_runtime in (None, "", "NO_DAILY_ARTIFACT"):
            runtime_status = "WARN"
            runtime_reason = "current_runtime_action_not_observable"
        add_metric(
            "runtime_action",
            current_runtime,
            previous_runtime,
            None,
            runtime_status,
            runtime_reason,
        )

        warn_rows = [row for row in rows if row.get("status") == "WARN"]
        if selected_overlap_ratio is not None:
            summary.append(f"selected_overlap={self._fmt_percent(selected_overlap_ratio, 2)}")
        if holding_overlap_ratio is not None:
            summary.append(f"holding_overlap={self._fmt_percent(holding_overlap_ratio, 2)}")
        if current_mainline.get("tag"):
            summary.append(f"top_mainline={current_mainline.get('tag')}({current_mainline.get('match')})")
        status = "WARN" if warn_rows else "PASS"
        reason = f"previous_report_date={self._json_default(previous_report_date)},expected_previous_report_date={self._json_default(expected_previous_report_date)},warn={len(warn_rows)}"
        return {
            "status": status,
            "reason": reason,
            "previous_report_date": previous_report_date,
            "previous_report_path": str(previous_path) if previous_path else None,
            "expected_previous_report_date": expected_previous_report_date,
            "lookup_reason": previous_lookup_reason,
            "scope": "production_daily_diff_observation",
            "rows": rows,
            "summary": summary,
        }

    def _load_previous_report_payload(
        self,
        *,
        output_root: Path,
        report_date: date,
    ) -> tuple[dict[str, Any] | None, Path | None, str]:
        previous_trade_date = self._resolve_signal_as_of_date(report_date)
        candidates: list[Path] = []
        if previous_trade_date and previous_trade_date != report_date:
            candidates.append(output_root / previous_trade_date.isoformat() / f"production_daily_observation_{previous_trade_date.isoformat()}.json")
        candidates.append(output_root / "latest" / "production_daily_observation_latest.json")

        for candidate in candidates:
            payload = self._read_report_payload_if_previous(candidate, report_date=report_date)
            if payload is not None:
                return payload, candidate, "previous_report_found"

        if output_root.exists():
            dated_candidates = sorted(
                output_root.glob("20??-??-??/production_daily_observation_20??-??-??.json"),
                reverse=True,
            )
            for candidate in dated_candidates:
                payload = self._read_report_payload_if_previous(candidate, report_date=report_date)
                if payload is not None:
                    return payload, candidate, "previous_report_found_by_scan"
        return None, candidates[0] if candidates else None, "previous_report_not_found"

    def _read_report_payload_if_previous(self, path: Path, *, report_date: date) -> dict[str, Any] | None:
        if not path.exists() or not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        payload_report_date = self._to_date(payload.get("report_date"))
        if payload_report_date is None or payload_report_date >= report_date:
            return None
        return payload

    @classmethod
    def _first_campaign_payload(cls, payload: dict[str, Any]) -> dict[str, Any]:
        campaigns = payload.get("campaigns") or []
        return campaigns[0] if campaigns and isinstance(campaigns[0], dict) else {}

    @classmethod
    def _instrument_code_set(cls, rows: list[dict[str, Any]]) -> set[str]:
        values: set[str] = set()
        for row in rows:
            value = row.get("instrument_code") or row.get("symbol") or row.get("instrument_id")
            if value is not None:
                values.add(str(value))
        return values

    @classmethod
    def _top_mainline_summary(cls, payload: dict[str, Any]) -> dict[str, Any]:
        alignments = ((payload.get("market_context") or {}).get("strategy_alignment") or [])
        first_alignment = alignments[0] if alignments and isinstance(alignments[0], dict) else {}
        match = (first_alignment.get("market_match_summary") or {}) if isinstance(first_alignment, dict) else {}
        return {
            "tag": match.get("top_exposure_tag"),
            "match": match.get("top_exposure_match_status"),
        }

    @classmethod
    def _derive_stock_exposure_from_snapshot(cls, snapshot: dict[str, Any]) -> Decimal | None:
        cash_ratio = cls._safe_ratio(snapshot.get("cash_balance"), snapshot.get("total_equity"))
        if cash_ratio is None:
            return None
        return Decimal("1") - cash_ratio

    @classmethod
    def _build_report_self_check(cls, payload: dict[str, Any]) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []

        def add(check_name: str, status: str, reason: str) -> None:
            rows.append({"check_name": check_name, "status": status, "reason": reason})

        required_fields = ["report_date", "signal_as_of_date", "overall_status", "generated_at", "production_campaign_count"]
        missing = [field for field in required_fields if payload.get(field) in (None, "")]
        add(
            "metadata_required_fields",
            "PASS" if not missing else "FAIL",
            "all_required_fields_present" if not missing else "missing=" + ",".join(missing),
        )

        daily_conclusion = payload.get("daily_conclusion") or []
        add(
            "daily_conclusion_rows_present",
            "PASS" if daily_conclusion else "WARN",
            f"daily_conclusion_count={len(daily_conclusion)}",
        )
        portfolio_rows = [row for row in daily_conclusion if row.get("item") == "组合表现"]
        portfolio_summary = str((portfolio_rows[0] or {}).get("summary") if portfolio_rows else "")
        missing_portfolio_metric_tokens = [
            token
            for token in [
                "daily_return=UNKNOWN",
                "daily_pnl=UNKNOWN",
                "cash_ratio=UNKNOWN",
                "stock_exposure=UNKNOWN",
                "cash_ratio=,",
                "cash_ratio=.",
                "cash_ratio=, ",
            ]
            if token in portfolio_summary
        ]
        add(
            "daily_conclusion_cash_ratio_not_blank",
            "PASS" if portfolio_rows and not missing_portfolio_metric_tokens else "WARN",
            (portfolio_summary or "portfolio_summary_missing")
            + (";missing_tokens=" + ",".join(missing_portfolio_metric_tokens) if missing_portfolio_metric_tokens else ""),
        )

        next_trade_plan = payload.get("next_trade_plan") or {}
        add(
            "next_trade_plan_top_plan_basis_present",
            "PASS" if next_trade_plan.get("plan_basis") else "WARN",
            f"plan_basis={next_trade_plan.get('plan_basis')}",
        )
        campaign_plan_missing = [
            str(plan.get("campaign_code") or "unknown")
            for plan in (next_trade_plan.get("campaigns") or [])
            if not plan.get("plan_basis")
        ]
        add(
            "next_trade_plan_campaign_plan_basis_present",
            "PASS" if not campaign_plan_missing else "WARN",
            "all_campaign_plan_basis_present" if not campaign_plan_missing else "missing=" + ",".join(campaign_plan_missing),
        )

        checks = payload.get("checks") or []
        missing_check_reason = [
            str(check.get("check_name") or "unknown")
            for check in checks
            if not check.get("status") or not check.get("reason")
        ]
        add(
            "checks_have_status_and_reason",
            "PASS" if checks and not missing_check_reason else "WARN",
            f"checks={len(checks)}" if not missing_check_reason else "missing=" + ",".join(missing_check_reason),
        )

        campaigns = payload.get("campaigns") or []
        add(
            "active_campaign_section_present",
            "PASS" if campaigns else "FAIL",
            f"campaign_count={len(campaigns)}",
        )

        buy_price_quality = payload.get("buy_price_quality") or {}
        add(
            "buy_price_quality_section_present",
            "PASS" if buy_price_quality.get("campaigns") else "WARN",
            str(buy_price_quality.get("reason") or "buy_price_quality_missing"),
        )

        daily_diff = payload.get("daily_diff") or {}
        add(
            "daily_diff_section_present",
            "PASS" if daily_diff.get("rows") else "WARN",
            str(daily_diff.get("reason") or "daily_diff_missing"),
        )

        statuses = [row.get("status") for row in rows]
        status = "FAIL" if "FAIL" in statuses else ("WARN" if "WARN" in statuses else "PASS")
        return {"status": status, "reason": f"fail={statuses.count('FAIL')},warn={statuses.count('WARN')}", "rows": rows}

    def _build_artifact_integrity(self, *, project_root: Path, artifact_index: list[dict[str, Any]]) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        for artifact in artifact_index:
            raw_path = str(artifact.get("path") or "")
            normalized_path = raw_path.replace("\\", "/")
            path = project_root / normalized_path if normalized_path else project_root
            exists = path.exists()
            size_bytes = path.stat().st_size if exists and path.is_file() else None
            modified_at = datetime.utcfromtimestamp(path.stat().st_mtime).isoformat() if exists else None
            parse_status = "NOT_APPLICABLE"
            parse_reason = "not_json_file"
            if exists and path.is_file() and path.suffix.lower() == ".json":
                try:
                    json.loads(path.read_text(encoding="utf-8"))
                    parse_status = "PASS"
                    parse_reason = "json_parse_ok"
                except Exception as exc:
                    parse_status = "FAIL"
                    parse_reason = f"json_parse_failed:{type(exc).__name__}:{exc}"
            elif exists and path.is_file() and size_bytes == 0:
                parse_status = "WARN"
                parse_reason = "empty_file"

            if not exists:
                row_status = "WARN"
                row_reason = "artifact_path_missing"
            elif path.is_file() and size_bytes == 0:
                row_status = "WARN"
                row_reason = "artifact_file_empty"
            elif parse_status == "FAIL":
                row_status = "FAIL"
                row_reason = parse_reason
            else:
                row_status = "PASS"
                row_reason = "artifact_accessible"

            rows.append({
                "campaign_code": artifact.get("campaign_code"),
                "artifact_type": artifact.get("artifact_type"),
                "path": raw_path,
                "exists": exists,
                "size_bytes": size_bytes,
                "modified_at": modified_at,
                "parse_status": parse_status,
                "status": row_status,
                "reason": row_reason,
            })
        statuses = [row.get("status") for row in rows]
        status = "FAIL" if "FAIL" in statuses else ("WARN" if "WARN" in statuses else "PASS")
        return {"status": status, "reason": f"artifact_count={len(rows)},fail={statuses.count('FAIL')},warn={statuses.count('WARN')}", "rows": rows}

    @classmethod
    def _build_action_priority(cls, payload: dict[str, Any]) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []

        def add(priority: str, status: str, item: str, reason: str, action: str) -> None:
            rows.append({"priority": priority, "status": status, "item": item, "reason": reason, "suggested_action": action})

        overall_status = str(payload.get("overall_status") or "WARN")
        if overall_status == "FAIL":
            add("P0", "FAIL", "overall_status", "生产日报 overall_status=FAIL", "先检查 FAIL check、campaign 状态和数据水位。")
        elif overall_status == "WARN":
            add("P1", "WARN", "overall_status", "生产日报 overall_status=WARN", "检查 WARN 项是否为可接受观察状态。")
        else:
            add("INFO", "PASS", "overall_status", "生产日报整体 PASS", "无需处理。")

        for check in payload.get("checks") or []:
            check_status = str(check.get("status") or "WARN")
            if check_status == "FAIL":
                add("P0", "FAIL", f"check:{check.get('check_name')}", str(check.get("reason") or ""), "优先修复该生产检查失败项。")
            elif check_status == "WARN":
                add("P1", "WARN", f"check:{check.get('check_name')}", str(check.get("reason") or ""), "当天处理或确认是否为预期 WARN。")

        next_trade_plan_sla = payload.get("next_trade_plan_sla") or {}
        if next_trade_plan_sla.get("status") == "FAIL":
            add("P0", "FAIL", "next_trade_plan_sla", str(next_trade_plan_sla.get("blocker") or ""), "检查 next_trade_date target/order 查询失败原因。")
        elif next_trade_plan_sla.get("status") == "WARN":
            add("P1", "WARN", "next_trade_plan_sla", str(next_trade_plan_sla.get("blocker") or ""), "确认 next_trade_date 计划生成链路是否已运行或是否尚未接入。")

        if payload.get("git_commit_status") == "WARN":
            add("P1", "WARN", "git_commit_traceability", "git_commit 无法追溯", "后续注入 Docker build git metadata。")

        report_self_check = payload.get("report_self_check") or {}
        if report_self_check.get("status") == "FAIL":
            add("P0", "FAIL", "report_self_check", str(report_self_check.get("reason") or ""), "先修复日报自身关键字段缺失。")
        elif report_self_check.get("status") == "WARN":
            add("P1", "WARN", "report_self_check", str(report_self_check.get("reason") or ""), "检查摘要字段、plan_basis、reason 是否完整。")

        artifact_integrity = payload.get("artifact_integrity") or {}
        if artifact_integrity.get("status") == "FAIL":
            add("P0", "FAIL", "artifact_integrity", str(artifact_integrity.get("reason") or ""), "检查产物 JSON/Markdown 是否损坏。")
        elif artifact_integrity.get("status") == "WARN":
            add("P1", "WARN", "artifact_integrity", str(artifact_integrity.get("reason") or ""), "检查产物是否缺失、为空或 latest 未更新。")

        daily_diff = payload.get("daily_diff") or {}
        if daily_diff.get("status") == "WARN":
            add("P2", "WARN", "daily_diff", str(daily_diff.get("reason") or ""), "查看昨日对比，确认是否为正常换仓/主线变化。")

        buy_price_quality = payload.get("buy_price_quality") or {}
        if buy_price_quality.get("status") == "WARN":
            add("P2", "WARN", "buy_price_quality", str(buy_price_quality.get("reason") or ""), "查看不利开盘跳空 Top，判断 NEXT_OPEN 成本影响。")

        market_context = payload.get("market_context") or {}
        breadth = market_context.get("breadth") or {}
        if breadth.get("market_breadth_state") == "BREADTH_WEAK":
            add("P2", "WARN", "market_breadth", "市场宽度偏弱", "观察组合是否连续跑输市场或高仓位暴露。")

        campaigns = payload.get("campaigns") or []
        first_campaign = campaigns[0] if campaigns else {}
        risk = first_campaign.get("risk_metrics") or {}
        snapshot = first_campaign.get("snapshot") or {}
        stock_exposure_value = risk.get("stock_exposure")
        if stock_exposure_value in (None, ""):
            cash_ratio = cls._safe_ratio(snapshot.get("cash_balance"), snapshot.get("total_equity"))
            if cash_ratio is not None:
                stock_exposure_value = Decimal("1") - cash_ratio
        stock_exposure = cls._to_decimal_value(stock_exposure_value)
        if stock_exposure is not None and stock_exposure >= Decimal("0.95"):
            add("P2", "WARN", "stock_exposure", f"stock_exposure={cls._fmt_percent(stock_exposure, 2)}", "市场偏弱时重点观察高仓位风险。")

        counts = {priority: len([row for row in rows if row.get("priority") == priority]) for priority in ("P0", "P1", "P2", "INFO")}
        status = "FAIL" if counts["P0"] else ("WARN" if counts["P1"] or counts["P2"] else "PASS")
        return {"status": status, "reason": f"P0={counts['P0']},P1={counts['P1']},P2={counts['P2']},INFO={counts['INFO']}", "counts": counts, "rows": rows}

    @classmethod
    def _build_daily_control_panel(cls, payload: dict[str, Any]) -> dict[str, Any]:
        action_priority = payload.get("action_priority") or {}
        next_trade_plan_sla = payload.get("next_trade_plan_sla") or {}
        report_self_check = payload.get("report_self_check") or {}
        artifact_integrity = payload.get("artifact_integrity") or {}
        daily_diff = payload.get("daily_diff") or {}
        buy_price_quality = payload.get("buy_price_quality") or {}
        market_context = payload.get("market_context") or {}
        breadth = market_context.get("breadth") or {}
        campaigns = payload.get("campaigns") or []
        first_campaign = campaigns[0] if campaigns else {}
        snapshot = first_campaign.get("snapshot") or {}
        risk = first_campaign.get("risk_metrics") or {}
        cash_ratio = risk.get("cash_ratio")
        if cash_ratio in (None, ""):
            cash_ratio = cls._safe_ratio(snapshot.get("cash_balance"), snapshot.get("total_equity"))
        stock_exposure = risk.get("stock_exposure")
        if stock_exposure in (None, ""):
            cash_ratio_decimal = cls._to_decimal_value(cash_ratio)
            if cash_ratio_decimal is not None:
                stock_exposure = Decimal("1") - cash_ratio_decimal
        top_action = next((row for row in action_priority.get("rows") or [] if row.get("priority") in {"P0", "P1"}), None)
        if top_action is None:
            top_action = next((row for row in action_priority.get("rows") or [] if row.get("priority") == "P2"), None)
        return {
            "status": action_priority.get("status") or payload.get("overall_status"),
            "action_required": bool(top_action and top_action.get("priority") in {"P0", "P1"}),
            "top_action": top_action,
            "overall_status": payload.get("overall_status"),
            "report_date": payload.get("report_date"),
            "signal_as_of_date": payload.get("signal_as_of_date"),
            "next_trade_date": payload.get("next_trade_date"),
            "next_trade_plan_status": next_trade_plan_sla.get("status"),
            "next_trade_plan_basis": next_trade_plan_sla.get("plan_basis"),
            "report_self_check_status": report_self_check.get("status"),
            "artifact_integrity_status": artifact_integrity.get("status"),
            "daily_diff_status": daily_diff.get("status"),
            "buy_price_quality_status": buy_price_quality.get("status"),
            "market_breadth_state": breadth.get("market_breadth_state"),
            "cash_ratio": cash_ratio,
            "stock_exposure": stock_exposure,
            "priority_counts": action_priority.get("counts") or {},
        }

    @classmethod
    def _build_manual_review_checklist(cls, payload: dict[str, Any]) -> list[dict[str, Any]]:
        next_trade_plan_sla = payload.get("next_trade_plan_sla") or {}
        daily_diff = payload.get("daily_diff") or {}
        buy_price_quality = payload.get("buy_price_quality") or {}
        market_context = payload.get("market_context") or {}
        breadth = market_context.get("breadth") or {}
        checklist = [
            {"priority": "P1", "checked": False, "item": "git_commit 是否真实可追溯", "reason": str(payload.get("git_commit_status"))},
            {"priority": "P1", "checked": False, "item": "next_trade_plan 是否已落表", "reason": str(next_trade_plan_sla.get("blocker") or "")},
            {"priority": "P2", "checked": False, "item": "market breadth 是否持续偏弱", "reason": str(breadth.get("market_breadth_state") or "UNKNOWN")},
            {"priority": "P2", "checked": False, "item": "昨日对比是否异常", "reason": str(daily_diff.get("reason") or "daily_diff_missing")},
            {"priority": "P2", "checked": False, "item": "NEXT_OPEN 买入价格质量是否异常", "reason": str(buy_price_quality.get("reason") or "buy_price_quality_missing")},
            {"priority": "P2", "checked": False, "item": "主线是否连续 NEUTRAL/WEAK", "reason": "需要主线错位连续观察阶段补充。"},
            {"priority": "P2", "checked": False, "item": "是否有接近退出条件的持仓", "reason": "当前仅为生产观察骨架，正式退出规则未落表。"},
            {"priority": "P1", "checked": False, "item": "是否有订单/成交异常", "reason": "查看 Production Paper Campaigns 和风险 / 异常检查。"},
            {"priority": "P2", "checked": False, "item": "是否需要进入研究端复盘", "reason": "若连续跑输、主线错位或选股大换血，再进入研究端复盘。"},
        ]
        if payload.get("overall_status") == "PASS":
            checklist.insert(0, {"priority": "INFO", "checked": False, "item": "确认生产日报整体 PASS", "reason": "overall_status=PASS"})
        return checklist

    def _build_market_context(
        self,
        *,
        report_date: date,
        campaign_reports: list[dict[str, Any]],
        detail_limit: int,
    ) -> dict[str, Any]:
        """Build market-wide context for production daily observation.

        This is production observation context, not a research conclusion. It uses
        stable production base-data tables and gracefully degrades when industry or
        concept tags are unavailable.
        """
        breadth = self._market_breadth(report_date=report_date)
        index_overview = self._market_index_overview(report_date=report_date, limit=20)
        strong_stocks = self._market_stock_extremes(report_date=report_date, order="strong", limit=min(detail_limit, 30))
        weak_stocks = self._market_stock_extremes(report_date=report_date, order="weak", limit=min(detail_limit, 30))
        industry_strength = self._tag_strength_summary(
            report_date=report_date,
            tag_type_pattern="SW_INDUSTRY_L2%",
            limit=15,
        )
        concept_strength = self._tag_strength_summary(
            report_date=report_date,
            tag_type_pattern="%CONCEPT%",
            limit=15,
        )
        strategy_alignment = self._strategy_market_alignment(
            report_date=report_date,
            campaign_reports=campaign_reports,
        )
        return {
            "report_date": report_date,
            "status": self._derive_market_context_status(
                breadth=breadth,
                index_overview=index_overview,
                strong_stocks=strong_stocks,
            ),
            "summary": self._market_context_summary(
                breadth=breadth,
                index_overview=index_overview,
                industry_strength=industry_strength,
                strategy_alignment=strategy_alignment,
            ),
            "breadth": breadth,
            "index_overview": index_overview,
            "strong_stocks": strong_stocks,
            "weak_stocks": weak_stocks,
            "industry_strength": industry_strength,
            "concept_strength": concept_strength,
            "strategy_alignment": strategy_alignment,
        }

    def _market_breadth(self, *, report_date: date) -> dict[str, Any]:
        sql = """
        with base as (
            select
                b.instrument_id,
                b.close,
                b.pre_close,
                b.amount,
                b.volume,
                b.turnover_rate,
                b.is_suspended,
                case
                    when b.pct_change is not null then b.pct_change / 100.0
                    when b.pre_close is null or b.pre_close = 0 then null
                    else b.close / b.pre_close - 1
                end as pct_change,
                l.up_limit,
                l.down_limit
            from public.core_daily_bar b
            left join public.core_price_limit_daily l
              on l.instrument_id = b.instrument_id
             and l.trade_date = b.trade_date
            where b.trade_date = :report_date
              and coalesce(b.is_suspended, false) = false
        )
        select
            count(*) as total_rows,
            count(*) filter (where pct_change > 0) as up_rows,
            count(*) filter (where pct_change < 0) as down_rows,
            count(*) filter (where pct_change = 0) as flat_rows,
            count(*) filter (where pct_change >= 0.03) as up_3pct_rows,
            count(*) filter (where pct_change >= 0.05) as up_5pct_rows,
            count(*) filter (where pct_change <= -0.03) as down_3pct_rows,
            count(*) filter (where pct_change <= -0.05) as down_5pct_rows,
            count(*) filter (where up_limit is not null and close >= up_limit) as limit_up_rows,
            count(*) filter (where down_limit is not null and close <= down_limit) as limit_down_rows,
            count(*) filter (where up_limit is not null and close < up_limit and close >= up_limit * 0.98) as near_limit_up_rows,
            count(*) filter (where down_limit is not null and close > down_limit and close <= down_limit * 1.02) as near_limit_down_rows,
            avg(pct_change) as avg_pct_change,
            percentile_cont(0.5) within group (order by pct_change) as median_pct_change,
            sum(amount) as total_amount
        from base
        """
        row = self._one_or_none(sql, {"report_date": report_date}) or {}
        total = self._to_decimal_value(row.get("total_rows"))
        up = self._to_decimal_value(row.get("up_rows"))
        down = self._to_decimal_value(row.get("down_rows"))
        row["up_ratio"] = (up / total) if total and up is not None else None
        row["down_ratio"] = (down / total) if total and down is not None else None
        row["market_breadth_state"] = self._classify_breadth(row)
        return row

    def _market_index_overview(self, *, report_date: date, limit: int) -> list[dict[str, Any]]:
        sql_with_dim = """
        with curr as (
            select * from public.market_index_bar where trade_date = :report_date
        ), prev as (
            select distinct on (market_index_id)
                market_index_id,
                close as prev_close
            from public.market_index_bar
            where trade_date < :report_date
            order by market_index_id, trade_date desc
        )
        select
            c.market_index_id,
            coalesce(mi.index_code, mi.symbol, ('index_' || c.market_index_id::text)) as index_code,
            coalesce(mi.display_name, mi.index_name, mi.name, ('index_' || c.market_index_id::text)) as index_name,
            c.close,
            p.prev_close,
            case when p.prev_close is null or p.prev_close = 0 then null else c.close / p.prev_close - 1 end as pct_change,
            c.volume,
            c.turnover
        from curr c
        left join prev p on p.market_index_id = c.market_index_id
        left join public.market_index mi on mi.id = c.market_index_id
        order by c.market_index_id
        limit :limit
        """
        fallback_sql = """
        with curr as (
            select * from public.market_index_bar where trade_date = :report_date
        ), prev as (
            select distinct on (market_index_id)
                market_index_id,
                close as prev_close
            from public.market_index_bar
            where trade_date < :report_date
            order by market_index_id, trade_date desc
        )
        select
            c.market_index_id,
            ('index_' || c.market_index_id::text) as index_code,
            ('index_' || c.market_index_id::text) as index_name,
            c.close,
            p.prev_close,
            case when p.prev_close is null or p.prev_close = 0 then null else c.close / p.prev_close - 1 end as pct_change,
            c.volume,
            c.turnover
        from curr c
        left join prev p on p.market_index_id = c.market_index_id
        order by c.market_index_id
        limit :limit
        """
        try:
            return self._rows(sql_with_dim, {"report_date": report_date, "limit": limit})
        except Exception:
            self._rollback_session_safely()
            try:
                return self._rows(fallback_sql, {"report_date": report_date, "limit": limit})
            except Exception:
                self._rollback_session_safely()
                return []

    def _market_stock_extremes(self, *, report_date: date, order: str, limit: int) -> list[dict[str, Any]]:
        direction = "desc" if order == "strong" else "asc"
        sql = f"""
        select
            b.instrument_id,
            mi.instrument_code,
            mi.symbol,
            mi.display_name,
            b.close,
            b.pre_close,
            case
                    when b.pct_change is not null then b.pct_change / 100.0
                    when b.pre_close is null or b.pre_close = 0 then null
                    else b.close / b.pre_close - 1
                end as pct_change,
            b.amount,
            b.volume,
            b.turnover_rate,
            l.up_limit,
            l.down_limit,
            case when l.up_limit is not null and b.close >= l.up_limit then true else false end as is_limit_up,
            case when l.down_limit is not null and b.close <= l.down_limit then true else false end as is_limit_down
        from public.core_daily_bar b
        left join public.meta_instrument mi on mi.id = b.instrument_id
        left join public.core_price_limit_daily l
          on l.instrument_id = b.instrument_id
         and l.trade_date = b.trade_date
        where b.trade_date = :report_date
          and coalesce(b.is_suspended, false) = false
          and b.pre_close is not null
          and b.pre_close <> 0
        order by pct_change {direction} nulls last, b.amount desc nulls last
        limit :limit
        """
        return self._rows(sql, {"report_date": report_date, "limit": limit})

    def _tag_strength_summary(self, *, report_date: date, tag_type_pattern: str, limit: int) -> dict[str, Any]:
        sql = """
        with stock_ret as (
            select
                b.instrument_id,
                b.close,
                case
                    when b.pct_change is not null then b.pct_change / 100.0
                    when b.pre_close is null or b.pre_close = 0 then null
                    else b.close / b.pre_close - 1
                end as pct_change,
                b.amount,
                l.up_limit,
                l.down_limit
            from public.core_daily_bar b
            left join public.core_price_limit_daily l
              on l.instrument_id = b.instrument_id
             and l.trade_date = b.trade_date
            where b.trade_date = :report_date
              and coalesce(b.is_suspended, false) = false
        ), tag_rows as (
            select
                t.tag_type,
                t.tag_code,
                t.tag_name,
                sr.instrument_id,
                sr.close,
                sr.pct_change,
                sr.amount,
                sr.up_limit,
                sr.down_limit
            from stock_ret sr
            join public.instrument_tag it
              on it.instrument_id = sr.instrument_id
             and it.effective_from <= :report_date
             and (it.effective_to is null or it.effective_to >= :report_date)
            join public.tag t on t.id = it.tag_id
            where t.is_active = true
              and t.tag_type like :tag_type_pattern
        ), agg as (
            select
                tag_type,
                tag_code,
                tag_name,
                count(*) as instrument_count,
                count(*) filter (where pct_change > 0) as up_rows,
                count(*) filter (where pct_change < 0) as down_rows,
                avg(pct_change) as avg_pct_change,
                percentile_cont(0.5) within group (order by pct_change) as median_pct_change,
                sum(amount) as total_amount,
                count(*) filter (where up_limit is not null and close >= up_limit) as limit_up_rows,
                count(*) filter (where down_limit is not null and close <= down_limit) as limit_down_rows
            from tag_rows
            group by tag_type, tag_code, tag_name
            having count(*) >= 5
        )
        select *
        from agg
        order by avg_pct_change desc nulls last, total_amount desc nulls last
        limit :limit
        """
        try:
            rows = self._rows(sql, {"report_date": report_date, "tag_type_pattern": tag_type_pattern, "limit": limit})
        except Exception as exc:
            self._rollback_session_safely()
            return {"status": "WARN", "reason": f"query_failed:{type(exc).__name__}:{exc}", "rows": []}
        if not rows:
            return {"status": "WARN", "reason": "no_matching_tag_data", "rows": []}
        return {"status": "PASS", "reason": f"rows={len(rows)}", "rows": rows}

    def _strategy_market_alignment(self, *, report_date: date, campaign_reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for campaign in campaign_reports:
            selected_items = campaign.get("selected_instruments") or []
            holding_items = campaign.get("positions_preview") or []
            selected_ids = [item.get("instrument_id") for item in selected_items if item.get("instrument_id") is not None]
            holding_ids = [item.get("instrument_id") for item in holding_items if item.get("instrument_id") is not None]
            industry_exposure = self._campaign_tag_exposure(
                report_date=report_date,
                selected_items=selected_items,
                holding_items=holding_items,
                tag_type_pattern="SW_INDUSTRY_L2%",
                limit=12,
            )
            concept_exposure = self._campaign_tag_exposure(
                report_date=report_date,
                selected_items=selected_items,
                holding_items=holding_items,
                tag_type_pattern="%CONCEPT%",
                limit=12,
            )
            rows.append({
                "campaign_code": campaign.get("campaign_code"),
                "portfolio_id": campaign.get("portfolio_id"),
                "selected_market_stats": self._instrument_market_stats(report_date=report_date, instrument_ids=selected_ids),
                "holding_market_stats": self._instrument_market_stats(report_date=report_date, instrument_ids=holding_ids),
                "industry_exposure": industry_exposure,
                "concept_exposure": concept_exposure,
                "market_match_summary": self._campaign_market_match_summary(
                    industry_exposure=industry_exposure,
                    concept_exposure=concept_exposure,
                ),
            })
        return rows

    def _campaign_tag_exposure(
        self,
        *,
        report_date: date,
        selected_items: list[dict[str, Any]],
        holding_items: list[dict[str, Any]],
        tag_type_pattern: str,
        limit: int,
    ) -> dict[str, Any]:
        """Aggregate selected/holding exposure by market tag.

        This intentionally uses the existing public.tag / public.instrument_tag
        schema only: tag_type, tag_code, tag_name, taxonomy_source, is_active.
        It avoids category/tag_source columns because they do not exist in the
        current production schema.
        """
        selected_weights: dict[int, Decimal] = {}
        for item in selected_items:
            instrument_id = item.get("instrument_id")
            if instrument_id is None:
                continue
            value = self._to_decimal_value(item.get("target_weight")) or Decimal("0")
            selected_weights[int(instrument_id)] = selected_weights.get(int(instrument_id), Decimal("0")) + value

        holding_weights: dict[int, Decimal] = {}
        holding_values: dict[int, Decimal] = {}
        holding_pnl: dict[int, Decimal] = {}
        for item in holding_items:
            instrument_id = item.get("instrument_id")
            if instrument_id is None:
                continue
            iid = int(instrument_id)
            holding_weights[iid] = holding_weights.get(iid, Decimal("0")) + (self._to_decimal_value(item.get("position_weight")) or Decimal("0"))
            holding_values[iid] = holding_values.get(iid, Decimal("0")) + (self._to_decimal_value(item.get("market_value")) or Decimal("0"))
            holding_pnl[iid] = holding_pnl.get(iid, Decimal("0")) + (self._to_decimal_value(item.get("total_pnl")) or Decimal("0"))

        instrument_ids = sorted(set(selected_weights) | set(holding_weights))
        if not instrument_ids:
            return {"status": "WARN", "reason": "no_selected_or_holding_instruments", "rows": []}

        tag_sql = """
        select
            it.instrument_id,
            t.tag_type,
            t.tag_code,
            t.tag_name
        from public.instrument_tag it
        join public.tag t on t.id = it.tag_id
        where it.instrument_id = any(:instrument_ids)
          and t.is_active = true
          and t.tag_type like :tag_type_pattern
          and it.effective_from <= :report_date
          and (it.effective_to is null or it.effective_to >= :report_date)
        """
        try:
            tag_rows = self._rows(
                tag_sql,
                {
                    "instrument_ids": instrument_ids,
                    "tag_type_pattern": tag_type_pattern,
                    "report_date": report_date,
                },
            )
        except Exception as exc:
            self._rollback_session_safely()
            return {"status": "WARN", "reason": f"query_failed:{type(exc).__name__}:{exc}", "rows": []}

        if not tag_rows:
            return {"status": "WARN", "reason": "no_matching_tag_data", "rows": []}

        market_strength = self._tag_strength_summary(
            report_date=report_date,
            tag_type_pattern=tag_type_pattern,
            limit=1000,
        )
        market_map: dict[tuple[Any, Any, Any], dict[str, Any]] = {}
        for row in market_strength.get("rows") or []:
            key = (row.get("tag_type"), row.get("tag_code"), row.get("tag_name"))
            market_map[key] = row

        grouped: dict[tuple[Any, Any, Any], dict[str, Any]] = {}
        for row in tag_rows:
            iid = int(row.get("instrument_id"))
            key = (row.get("tag_type"), row.get("tag_code"), row.get("tag_name"))
            item = grouped.setdefault(
                key,
                {
                    "tag_type": row.get("tag_type"),
                    "tag_code": row.get("tag_code"),
                    "tag_name": row.get("tag_name"),
                    "selected_count": 0,
                    "selected_weight": Decimal("0"),
                    "holding_count": 0,
                    "holding_weight": Decimal("0"),
                    "holding_market_value": Decimal("0"),
                    "holding_total_pnl": Decimal("0"),
                },
            )
            if iid in selected_weights:
                item["selected_count"] += 1
                item["selected_weight"] += selected_weights[iid]
            if iid in holding_weights:
                item["holding_count"] += 1
                item["holding_weight"] += holding_weights[iid]
                item["holding_market_value"] += holding_values.get(iid, Decimal("0"))
                item["holding_total_pnl"] += holding_pnl.get(iid, Decimal("0"))

        rows: list[dict[str, Any]] = []
        for key, item in grouped.items():
            market = market_map.get(key) or {}
            item["market_instrument_count"] = market.get("instrument_count")
            item["market_avg_pct_change"] = market.get("avg_pct_change")
            item["market_median_pct_change"] = market.get("median_pct_change")
            item["market_limit_up_rows"] = market.get("limit_up_rows")
            item["market_total_amount"] = market.get("total_amount")
            item["match_status"] = self._classify_tag_match(item)
            rows.append(item)

        rows.sort(
            key=lambda x: (
                self._to_decimal_value(x.get("selected_weight")) or Decimal("0"),
                self._to_decimal_value(x.get("holding_weight")) or Decimal("0"),
                self._to_decimal_value(x.get("market_avg_pct_change")) or Decimal("-999"),
            ),
            reverse=True,
        )
        limited_rows = rows[:limit]
        if not limited_rows:
            return {"status": "WARN", "reason": "no_aggregated_tag_rows", "rows": []}
        return {"status": "PASS", "reason": f"rows={len(limited_rows)}", "rows": limited_rows}

    @classmethod
    def _classify_tag_match(cls, row: dict[str, Any]) -> str:
        avg_return = cls._to_decimal_value(row.get("market_avg_pct_change"))
        selected_count = int(row.get("selected_count") or 0)
        holding_count = int(row.get("holding_count") or 0)
        if avg_return is None:
            return "DATA_NOT_READY"
        if selected_count <= 0 and holding_count <= 0:
            return "NO_EXPOSURE"
        if avg_return >= Decimal("0.01"):
            return "STRONG_MATCH"
        if avg_return <= Decimal("-0.01"):
            return "WEAK_EXPOSURE"
        return "NEUTRAL"

    @classmethod
    def _campaign_market_match_summary(
        cls,
        *,
        industry_exposure: dict[str, Any],
        concept_exposure: dict[str, Any],
    ) -> dict[str, Any]:
        industry_rows = [
            row for row in (industry_exposure.get("rows") or [])
            if int(row.get("selected_count") or 0) > 0 or int(row.get("holding_count") or 0) > 0
        ]
        concept_rows = [
            row for row in (concept_exposure.get("rows") or [])
            if int(row.get("selected_count") or 0) > 0 or int(row.get("holding_count") or 0) > 0
        ]
        main_theme_rows = industry_rows + [row for row in concept_rows if not cls._is_generic_theme_tag(row)]
        generic_rows = [row for row in concept_rows if cls._is_generic_theme_tag(row)]
        strong_rows = [row for row in main_theme_rows if row.get("match_status") == "STRONG_MATCH"]
        weak_rows = [row for row in main_theme_rows if row.get("match_status") == "WEAK_EXPOSURE"]
        top_mainline = None
        if main_theme_rows:
            top_mainline = max(
                main_theme_rows,
                key=lambda row: (
                    cls._to_decimal_value(row.get("selected_weight")) or Decimal("0"),
                    cls._to_decimal_value(row.get("holding_weight")) or Decimal("0"),
                    cls._to_decimal_value(row.get("market_avg_pct_change")) or Decimal("-999"),
                ),
            )
        top_generic = None
        if generic_rows:
            top_generic = max(
                generic_rows,
                key=lambda row: (
                    cls._to_decimal_value(row.get("selected_weight")) or Decimal("0"),
                    cls._to_decimal_value(row.get("holding_weight")) or Decimal("0"),
                ),
            )
        if weak_rows and not strong_rows:
            status = "WARN"
            reason = "main_theme_exposure_skews_to_weak_tags"
        elif strong_rows:
            status = "PASS"
            reason = "has_strong_main_theme_exposure"
        elif main_theme_rows:
            status = "PASS"
            reason = "main_theme_exposure_neutral"
        else:
            status = "WARN"
            reason = "no_main_theme_exposure"
        return {
            "status": status,
            "reason": reason,
            "strong_tag_count": len(strong_rows),
            "weak_tag_count": len(weak_rows),
            "main_theme_tag_count": len(main_theme_rows),
            "generic_tag_filtered_count": len(generic_rows),
            "top_exposure_tag": (top_mainline or {}).get("tag_name"),
            "top_exposure_tag_type": (top_mainline or {}).get("tag_type"),
            "top_exposure_match_status": (top_mainline or {}).get("match_status"),
            "top_generic_tag_filtered": (top_generic or {}).get("tag_name"),
        }

    @classmethod
    def _is_generic_theme_tag(cls, row: dict[str, Any]) -> bool:
        tag_name = str(row.get("tag_name") or "").strip()
        tag_type = str(row.get("tag_type") or "").strip()
        if tag_type.startswith("SW_INDUSTRY"):
            return False
        if tag_name in cls.GENERIC_THEME_TAG_NAMES:
            return True
        return any(keyword and keyword in tag_name for keyword in cls.GENERIC_THEME_TAG_KEYWORDS)

    def _instrument_market_stats(self, *, report_date: date, instrument_ids: list[Any]) -> dict[str, Any]:
        cleaned_ids = [int(x) for x in instrument_ids if x is not None]
        if not cleaned_ids:
            return {"instrument_count": 0, "status": "WARN", "reason": "no_instruments"}
        sql = """
        select
            count(*) as instrument_count,
            count(*) filter (where pct_change > 0) as up_rows,
            count(*) filter (where pct_change < 0) as down_rows,
            avg(pct_change) as avg_pct_change,
            count(*) filter (where up_limit is not null and close >= up_limit) as limit_up_rows,
            count(*) filter (where down_limit is not null and close <= down_limit) as limit_down_rows,
            sum(amount) as total_amount
        from (
            select
                b.instrument_id,
                b.close,
                b.amount,
                case
                    when b.pct_change is not null then b.pct_change / 100.0
                    when b.pre_close is null or b.pre_close = 0 then null
                    else b.close / b.pre_close - 1
                end as pct_change,
                l.up_limit,
                l.down_limit
            from public.core_daily_bar b
            left join public.core_price_limit_daily l
              on l.instrument_id = b.instrument_id
             and l.trade_date = b.trade_date
            where b.trade_date = :report_date
              and b.instrument_id = any(:instrument_ids)
        ) x
        """
        row = self._one_or_none(sql, {"report_date": report_date, "instrument_ids": cleaned_ids}) or {}
        row["status"] = "PASS" if row.get("instrument_count") else "WARN"
        row["reason"] = "market_stats_ready" if row.get("instrument_count") else "no_market_rows"
        return row

    def _build_return_attribution(
        self,
        *,
        campaign_reports: list[dict[str, Any]],
        market_context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Build a production-observation return attribution skeleton.

        This is intentionally a lightweight operational attribution. It uses
        already-built campaign rows, position PnL, tag exposure PnL, and market
        context. It does not perform research-style factor attribution or alpha
        decomposition.
        """
        alignment_map = {
            str(item.get("campaign_code") or ""): item
            for item in (market_context.get("strategy_alignment") or [])
            if item.get("campaign_code") is not None
        }
        breadth = market_context.get("breadth") or {}
        market_avg_return = self._to_decimal_value(breadth.get("avg_pct_change"))
        rows: list[dict[str, Any]] = []
        for campaign in campaign_reports:
            campaign_code = str(campaign.get("campaign_code") or "")
            snapshot = campaign.get("snapshot") or {}
            risk = campaign.get("risk_metrics") or {}
            alignment = alignment_map.get(campaign_code) or {}
            selected_stats = alignment.get("selected_market_stats") or {}
            holding_stats = alignment.get("holding_market_stats") or {}
            market_match = alignment.get("market_match_summary") or {}

            portfolio_return = self._to_decimal_value(snapshot.get("daily_return"))
            selected_avg_return = self._to_decimal_value(selected_stats.get("avg_pct_change"))
            holding_avg_return = self._to_decimal_value(holding_stats.get("avg_pct_change"))

            position_rows = [row for row in (campaign.get("positions_preview") or []) if row.get("total_pnl") is not None]
            gain_rows = sorted(
                position_rows,
                key=lambda row: self._to_decimal_value(row.get("total_pnl")) or Decimal("0"),
                reverse=True,
            )[:5]
            loss_rows = sorted(
                position_rows,
                key=lambda row: self._to_decimal_value(row.get("total_pnl")) or Decimal("0"),
            )[:5]

            industry_rows = (alignment.get("industry_exposure") or {}).get("rows") or []
            concept_rows = [
                row for row in ((alignment.get("concept_exposure") or {}).get("rows") or [])
                if not self._is_generic_theme_tag(row)
            ]
            industry_top = self._attribution_top_bottom_rows(industry_rows, limit=5)
            concept_top = self._attribution_top_bottom_rows(concept_rows, limit=5)

            status = "PASS" if snapshot and position_rows else "WARN"
            reason = "position_and_tag_attribution_ready" if status == "PASS" else "missing_position_or_snapshot_for_attribution"
            rows.append({
                "campaign_code": campaign.get("campaign_code"),
                "portfolio_id": campaign.get("portfolio_id"),
                "status": status,
                "reason": reason,
                "scope": "production_observation_skeleton_not_research_attribution",
                "benchmark_context": {
                    "portfolio_daily_return": portfolio_return,
                    "portfolio_daily_pnl": snapshot.get("daily_pnl"),
                    "market_avg_return": market_avg_return,
                    "selected_avg_return": selected_avg_return,
                    "holding_avg_return": holding_avg_return,
                    "portfolio_vs_market": self._decimal_delta(portfolio_return, market_avg_return),
                    "selected_vs_market": self._decimal_delta(selected_avg_return, market_avg_return),
                    "holding_vs_market": self._decimal_delta(holding_avg_return, market_avg_return),
                    "market_breadth_state": breadth.get("market_breadth_state"),
                    "top_mainline_tag": market_match.get("top_exposure_tag"),
                    "top_mainline_match": market_match.get("top_exposure_match_status"),
                },
                "individual_top_contributors": self._position_contribution_rows(gain_rows, snapshot=snapshot),
                "individual_bottom_contributors": self._position_contribution_rows(loss_rows, snapshot=snapshot),
                "industry_contribution": industry_top,
                "concept_contribution": concept_top,
                "observation": self._attribution_observation_text(
                    campaign=campaign,
                    benchmark_context={
                        "portfolio_daily_return": portfolio_return,
                        "market_avg_return": market_avg_return,
                        "selected_avg_return": selected_avg_return,
                        "holding_avg_return": holding_avg_return,
                    },
                    industry_rows=industry_rows,
                    concept_rows=concept_rows,
                    risk=risk,
                ),
            })
        return rows

    @classmethod
    def _decimal_delta(cls, left: Any, right: Any) -> Decimal | None:
        left_dec = cls._to_decimal_value(left)
        right_dec = cls._to_decimal_value(right)
        if left_dec is None or right_dec is None:
            return None
        return left_dec - right_dec

    @classmethod
    def _position_contribution_rows(cls, rows: list[dict[str, Any]], *, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        total_equity = cls._to_decimal_value(snapshot.get("total_equity"))
        daily_pnl = cls._to_decimal_value(snapshot.get("daily_pnl"))
        output: list[dict[str, Any]] = []
        for row in rows:
            pnl = cls._to_decimal_value(row.get("total_pnl"))
            market_value = cls._to_decimal_value(row.get("market_value"))
            output.append({
                "instrument_id": row.get("instrument_id"),
                "instrument_code": row.get("instrument_code"),
                "symbol": row.get("symbol"),
                "display_name": row.get("display_name"),
                "market_value": market_value,
                "position_weight": cls._safe_ratio(market_value, total_equity),
                "total_pnl": pnl,
                "pnl_share": cls._safe_ratio(pnl, daily_pnl),
                "position_status": row.get("position_status"),
            })
        return output

    @classmethod
    def _attribution_top_bottom_rows(cls, rows: list[dict[str, Any]], *, limit: int) -> dict[str, list[dict[str, Any]]]:
        cleaned = [row for row in rows if row.get("holding_total_pnl") is not None]
        top = sorted(
            cleaned,
            key=lambda row: cls._to_decimal_value(row.get("holding_total_pnl")) or Decimal("0"),
            reverse=True,
        )[:limit]
        bottom = sorted(
            cleaned,
            key=lambda row: cls._to_decimal_value(row.get("holding_total_pnl")) or Decimal("0"),
        )[:limit]
        return {
            "top": [cls._attribution_tag_row(row) for row in top],
            "bottom": [cls._attribution_tag_row(row) for row in bottom],
        }

    @classmethod
    def _attribution_tag_row(cls, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "tag_type": row.get("tag_type"),
            "tag_code": row.get("tag_code"),
            "tag_name": row.get("tag_name"),
            "holding_count": row.get("holding_count"),
            "holding_weight": row.get("holding_weight"),
            "holding_market_value": row.get("holding_market_value"),
            "holding_total_pnl": row.get("holding_total_pnl"),
            "market_avg_pct_change": row.get("market_avg_pct_change"),
            "match_status": row.get("match_status"),
        }

    @classmethod
    def _attribution_observation_text(
        cls,
        *,
        campaign: dict[str, Any],
        benchmark_context: dict[str, Any],
        industry_rows: list[dict[str, Any]],
        concept_rows: list[dict[str, Any]],
        risk: dict[str, Any],
    ) -> list[str]:
        notes: list[str] = []
        campaign_code = campaign.get("campaign_code")
        portfolio_return = cls._to_decimal_value(benchmark_context.get("portfolio_daily_return"))
        market_return = cls._to_decimal_value(benchmark_context.get("market_avg_return"))
        if portfolio_return is not None and market_return is not None:
            delta = portfolio_return - market_return
            notes.append(
                f"campaign={campaign_code} portfolio_vs_market={cls._fmt_percent(delta, 2)} "
                f"portfolio_return={cls._fmt_percent(portfolio_return, 4)} market_avg={cls._fmt_percent(market_return, 2)}"
            )
        strong_industry = [row.get("tag_name") for row in industry_rows if row.get("match_status") == "STRONG_MATCH"]
        weak_industry = [row.get("tag_name") for row in industry_rows if row.get("match_status") == "WEAK_EXPOSURE"]
        if strong_industry:
            notes.append("强势行业暴露：" + "、".join(cls._dedupe_strings(strong_industry)[:5]))
        if weak_industry:
            notes.append("弱势行业暴露：" + "、".join(cls._dedupe_strings(weak_industry)[:5]))
        strong_concept = [row.get("tag_name") for row in concept_rows if row.get("match_status") == "STRONG_MATCH" and not cls._is_generic_theme_tag(row)]
        weak_concept = [row.get("tag_name") for row in concept_rows if row.get("match_status") == "WEAK_EXPOSURE" and not cls._is_generic_theme_tag(row)]
        if strong_concept:
            notes.append("强势概念暴露：" + "、".join(cls._dedupe_strings(strong_concept)[:5]))
        if weak_concept:
            notes.append("弱势概念暴露：" + "、".join(cls._dedupe_strings(weak_concept)[:5]))
        total_pnl = risk.get("total_position_pnl")
        if total_pnl is not None:
            notes.append(f"持仓合计盈亏={cls._fmt_money(total_pnl)}，本节用于生产观察归因，不代表研究型 alpha 分解。")
        return notes

    @classmethod
    def _derive_market_context_status(
        cls,
        *,
        breadth: dict[str, Any],
        index_overview: list[dict[str, Any]],
        strong_stocks: list[dict[str, Any]],
    ) -> str:
        if not breadth or not breadth.get("total_rows"):
            return "FAIL"
        if not index_overview or not strong_stocks:
            return "WARN"
        return "PASS"

    @classmethod
    def _market_context_summary(
        cls,
        *,
        breadth: dict[str, Any],
        index_overview: list[dict[str, Any]],
        industry_strength: dict[str, Any],
        strategy_alignment: list[dict[str, Any]],
    ) -> list[str]:
        notes: list[str] = []
        if breadth:
            notes.append(
                "market_breadth="
                f"{breadth.get('market_breadth_state')} "
                f"up_ratio={cls._fmt_percent(breadth.get('up_ratio'), 2)} "
                f"limit_up={breadth.get('limit_up_rows')} limit_down={breadth.get('limit_down_rows')}"
            )
        if index_overview:
            lead = index_overview[0]
            notes.append(
                f"index_sample={lead.get('index_name') or lead.get('index_code')} pct_change={cls._fmt_percent(lead.get('pct_change'), 2)}"
            )
        if industry_strength.get("status") == "PASS" and industry_strength.get("rows"):
            lead = industry_strength["rows"][0]
            notes.append(
                f"strong_industry={lead.get('tag_name')} avg_pct_change={cls._fmt_percent(lead.get('avg_pct_change'), 2)}"
            )
        for item in strategy_alignment:
            selected = item.get("selected_market_stats") or {}
            holding = item.get("holding_market_stats") or {}
            notes.append(
                f"campaign={item.get('campaign_code')} selected_avg_return={cls._fmt_percent(selected.get('avg_pct_change'), 2)} "
                f"holding_avg_return={cls._fmt_percent(holding.get('avg_pct_change'), 2)}"
            )
            match = item.get("market_match_summary") or {}
            if match:
                notes.append(
                    f"campaign={item.get('campaign_code')} market_match={match.get('status')} "
                    f"reason={match.get('reason')} top_mainline={match.get('top_exposure_tag')} "
                    f"top_mainline_match={match.get('top_exposure_match_status')} "
                    f"generic_filtered={match.get('generic_tag_filtered_count')}"
                )
        return notes

    @classmethod
    def _render_market_observation_conclusion(cls, market_context: dict[str, Any]) -> list[str]:
        """Render production-style market observation conclusions.

        These conclusions are intentionally operational observations. They are derived
        from the report's own market context and strategy exposure rows; they are not
        research conclusions, alpha commentary, or trading advice.
        """
        breadth = market_context.get("breadth") or {}
        industry_rows = ((market_context.get("industry_strength") or {}).get("rows") or [])
        concept_rows = ((market_context.get("concept_strength") or {}).get("rows") or [])
        alignments = market_context.get("strategy_alignment") or []

        up_ratio = cls._to_decimal_value(breadth.get("up_ratio"))
        down_ratio = cls._to_decimal_value(breadth.get("down_ratio"))
        limit_up = cls._optional_int(breadth.get("limit_up_rows")) or 0
        limit_down = cls._optional_int(breadth.get("limit_down_rows")) or 0
        breadth_state = str(breadth.get("market_breadth_state") or "UNKNOWN")

        if up_ratio is None:
            market_bias = "市场宽度数据不足，暂不判断整体强弱。"
        elif up_ratio <= Decimal("0.40"):
            market_bias = "市场整体偏弱。"
        elif up_ratio >= Decimal("0.60"):
            market_bias = "市场整体偏强。"
        else:
            market_bias = "市场整体震荡。"

        breadth_detail = (
            f"上涨比例 {cls._fmt_percent(up_ratio, 2)}，"
            f"下跌比例 {cls._fmt_percent(down_ratio, 2)}，"
            f"涨停 {limit_up} 家，跌停 {limit_down} 家。"
        )
        if limit_down > limit_up and limit_down >= 10:
            money_effect = "跌停数量高于涨停数量，亏钱效应需要重点观察。"
        elif limit_up >= max(limit_down * 2, 10):
            money_effect = "涨停数量明显高于跌停数量，局部赚钱效应仍在。"
        else:
            money_effect = "涨跌停结构未出现极端失衡。"

        def _tag_name(row: dict[str, Any]) -> str:
            return str(row.get("tag_name") or row.get("tag") or "").strip()

        def _avg(row: dict[str, Any]) -> Decimal | None:
            return cls._to_decimal_value(row.get("avg_pct_change") or row.get("market_avg_pct_change"))

        strong_industries = [row for row in industry_rows if (_avg(row) is not None and _avg(row) >= Decimal("0.015"))]
        strong_concepts = [row for row in concept_rows if (_avg(row) is not None and _avg(row) >= Decimal("0.015") and not cls._is_generic_theme_tag(row))]
        weak_industries = [row for row in industry_rows if (_avg(row) is not None and _avg(row) <= Decimal("-0.01"))]
        weak_concepts = [row for row in concept_rows if (_avg(row) is not None and _avg(row) <= Decimal("-0.01") and not cls._is_generic_theme_tag(row))]

        strong_names = [_tag_name(row) for row in (strong_concepts[:3] + strong_industries[:2]) if _tag_name(row)]
        weak_names = [_tag_name(row) for row in (weak_concepts[:3] + weak_industries[:2]) if _tag_name(row)]
        if strong_names:
            strong_line = "强势方向：" + "、".join(cls._dedupe_strings(strong_names)[:5]) + "。"
        else:
            strong_line = "强势方向不集中，暂未形成清晰主线。"
        if weak_names:
            weak_line = "弱势方向：" + "、".join(cls._dedupe_strings(weak_names)[:5]) + "。"
        else:
            weak_line = "弱势方向未明显集中。"

        match_lines: list[str] = []
        risk_lines: list[str] = []
        focus_lines: list[str] = []
        for item in alignments:
            campaign_code = item.get("campaign_code")
            selected_stats = item.get("selected_market_stats") or {}
            selected_avg = cls._to_decimal_value(selected_stats.get("avg_pct_change"))
            selected_up = selected_stats.get("up_rows")
            selected_down = selected_stats.get("down_rows")
            summary = item.get("market_match_summary") or {}
            top_mainline = summary.get("top_exposure_tag")
            top_match = summary.get("top_exposure_match_status")
            strong_count = cls._optional_int(summary.get("strong_tag_count")) or 0
            weak_count = cls._optional_int(summary.get("weak_tag_count")) or 0

            if top_mainline:
                match_lines.append(
                    f"{campaign_code} 当前主线暴露为 {top_mainline}，匹配状态 {top_match or 'UNKNOWN'}。"
                )
            if selected_avg is not None:
                match_lines.append(
                    f"{campaign_code} 选股当日平均涨跌幅 {cls._fmt_percent(selected_avg, 2)}，上涨 {selected_up} 只，下跌 {selected_down} 只。"
                )
            if strong_count > 0 and weak_count > 0:
                match_lines.append(
                    f"{campaign_code} 同时存在强势暴露与弱势暴露，需要观察主线分化。"
                )
            elif strong_count > 0:
                match_lines.append(f"{campaign_code} 存在强势方向暴露。")
            elif weak_count > 0:
                match_lines.append(f"{campaign_code} 暴露更多偏向弱势方向。")

            exposure_rows: list[dict[str, Any]] = []
            for exposure_key in ("industry_exposure", "concept_exposure"):
                exposure_rows.extend((item.get(exposure_key) or {}).get("rows") or [])
            weak_exposure_names = [
                _tag_name(row)
                for row in exposure_rows
                if row.get("match_status") == "WEAK_EXPOSURE" and not cls._is_generic_theme_tag(row)
            ]
            strong_exposure_names = [
                _tag_name(row)
                for row in exposure_rows
                if row.get("match_status") == "STRONG_MATCH" and not cls._is_generic_theme_tag(row)
            ]
            if weak_exposure_names:
                risk_lines.append(
                    f"{campaign_code} 弱势暴露集中在：" + "、".join(cls._dedupe_strings(weak_exposure_names)[:4]) + "。"
                )
            if strong_exposure_names:
                focus_lines.append(
                    "关注强势暴露方向是否延续：" + "、".join(cls._dedupe_strings(strong_exposure_names)[:4]) + "。"
                )
            if top_mainline:
                focus_lines.append(f"关注 {top_mainline} 是否继续作为组合主线暴露。")

        if breadth_state == "BREADTH_WEAK" or (up_ratio is not None and up_ratio <= Decimal("0.40")):
            risk_lines.insert(0, "市场宽度偏弱，需关注弱势扩散对组合的拖累。")
        elif breadth_state == "BREADTH_STRONG":
            risk_lines.insert(0, "市场宽度偏强，需关注强势主线是否延续。")
        else:
            risk_lines.insert(0, "市场宽度中性，需观察主线轮动是否加快。")
        if limit_down > limit_up and limit_down >= 10:
            risk_lines.append("跌停压力偏高，需关注高波动方向回撤。")
        if strong_names:
            focus_lines.insert(0, "关注强势方向是否继续扩散：" + "、".join(cls._dedupe_strings(strong_names)[:4]) + "。")
        if weak_names:
            focus_lines.append("关注弱势方向是否继续拖累组合：" + "、".join(cls._dedupe_strings(weak_names)[:4]) + "。")

        if not match_lines:
            match_lines.append("策略与市场匹配数据不足，暂不生成适配度结论。")
        if not focus_lines:
            focus_lines.append("关注市场宽度、涨跌停结构和组合主线暴露的变化。")

        return [
            "",
            "### 2.9 市场观察结论",
            "",
            "#### 2.9.1 市场环境判断",
            "",
            f"- {market_bias}",
            f"- {breadth_detail}",
            f"- {money_effect}",
            "",
            "#### 2.9.2 当前主线状态",
            "",
            f"- {strong_line}",
            f"- {weak_line}",
            "",
            "#### 2.9.3 策略适配度观察",
            "",
            *[f"- {line}" for line in cls._dedupe_strings(match_lines)[:6]],
            "",
            "#### 2.9.4 风险提示",
            "",
            *[f"- {line}" for line in cls._dedupe_strings(risk_lines)[:6]],
            "",
            "#### 2.9.5 次日观察重点",
            "",
            *[f"- {line}" for line in cls._dedupe_strings(focus_lines)[:6]],
        ]

    @staticmethod
    def _classify_breadth(breadth: dict[str, Any]) -> str:
        up_ratio = ProductionDailyObservationReportBuilder._to_decimal_value(breadth.get("up_ratio"))
        limit_up = ProductionDailyObservationReportBuilder._optional_int(breadth.get("limit_up_rows")) or 0
        limit_down = ProductionDailyObservationReportBuilder._optional_int(breadth.get("limit_down_rows")) or 0
        if up_ratio is None:
            return "UNKNOWN"
        if up_ratio >= Decimal("0.60") and limit_up >= limit_down:
            return "BREADTH_STRONG"
        if up_ratio <= Decimal("0.40") or limit_down > limit_up * 2:
            return "BREADTH_WEAK"
        return "BREADTH_NEUTRAL"

    def _campaign_artifacts(self, project_root: Path, campaign_code: str) -> list[dict[str, Any]]:
        if not campaign_code:
            return []
        artifact_dirs = [
            ("m6_5_daily", project_root / "artifacts/m6_5/paper_campaign_daily"),
            ("m6_5_summary", project_root / "artifacts/m6_5/paper_campaign_summary"),
            ("m8_paper_chain", project_root / "artifacts/m8/paper_chain"),
            ("m8_portfolio_snapshot", project_root / "artifacts/m8/portfolio_snapshot"),
        ]
        rows: list[dict[str, Any]] = []
        for artifact_type, directory in artifact_dirs:
            if not directory.exists():
                rows.append({"artifact_type": artifact_type, "path": str(directory), "exists": False, "kind": "directory"})
                continue
            for path in sorted(directory.glob(f"*{campaign_code}*"))[-20:]:
                rows.append({
                    "artifact_type": artifact_type,
                    "path": str(path.relative_to(project_root)),
                    "exists": path.exists(),
                    "kind": "file",
                })
        return rows

    def _build_artifact_index(self, *, project_root: Path, campaigns: list[dict[str, Any]], report_date: date) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        runtime_log = project_root / "logs/daily_runtime.log"
        rows.append({
            "campaign_code": "__runtime__",
            "portfolio_id": None,
            "artifact_type": "daily_runtime_log",
            "path": str(runtime_log.relative_to(project_root)) if runtime_log.exists() else "logs/daily_runtime.log",
            "exists": runtime_log.exists(),
            "kind": "file",
        })
        for campaign in campaigns:
            campaign_code = str(campaign.get("campaign_code") or "")
            portfolio_id = campaign.get("portfolio_id")
            for artifact in self._campaign_artifacts(project_root, campaign_code):
                rows.append({"campaign_code": campaign_code, "portfolio_id": portfolio_id, **artifact})
            # Include latest portfolio-specific M8 artifacts even when filenames do not contain campaign_code.
            if portfolio_id is not None:
                for directory in [project_root / "artifacts/m8/paper_chain", project_root / "artifacts/m8/portfolio_snapshot"]:
                    if not directory.exists():
                        continue
                    for path in sorted(directory.glob(f"*p{portfolio_id}_*"))[-20:]:
                        rows.append({
                            "campaign_code": campaign_code,
                            "portfolio_id": portfolio_id,
                            "artifact_type": "m8_portfolio_related",
                            "path": str(path.relative_to(project_root)),
                            "exists": path.exists(),
                            "kind": "file",
                        })
        # Dedupe while preserving order.
        unique: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for row in rows:
            key = (str(row.get("campaign_code")), str(row.get("path")))
            if key in seen:
                continue
            seen.add(key)
            unique.append(row)
        return unique

    @staticmethod
    def _coerce_json_dict(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        return {}

    @staticmethod
    def _stats_value(stats: dict[str, Any], keys: tuple[str, ...]) -> Any:
        for key in keys:
            if key in stats:
                return stats.get(key)
        # Some stats payloads group counters under nested dictionaries. Search one level deep.
        for value in stats.values():
            if isinstance(value, dict):
                for key in keys:
                    if key in value:
                        return value.get(key)
        return None

    @classmethod
    def _trade_explanation_counts(cls, *, selection: dict[str, Any], orders: dict[str, Any], fills: dict[str, Any], snapshot: dict[str, Any], risk: dict[str, Any]) -> dict[str, Any]:
        selected_count = cls._optional_int(selection.get("selected_count")) or 0
        order_count = cls._optional_int((orders or {}).get("order_count")) or 0
        buy_count = cls._optional_int((orders or {}).get("buy_order_count")) or 0
        sell_count = cls._optional_int((orders or {}).get("sell_order_count")) or 0
        hold_count = cls._optional_int(risk.get("open_position_rows"))
        if hold_count is None:
            hold_count = cls._optional_int(snapshot.get("holding_count")) or 0
        skip_count = max(selected_count - order_count, 0)
        abnormal_orders = cls._optional_int((orders or {}).get("abnormal_order_count")) or 0
        abnormal_fills = cls._optional_int((fills or {}).get("abnormal_fill_count")) or 0
        entry_policy = cls._dedupe_join(
            [
                (orders or {}).get("entry_policy"),
                (fills or {}).get("fill_policy"),
                f"fill_price_source={(fills or {}).get('fill_price_source')}" if (fills or {}).get("fill_price_source") else None,
            ],
            separator=";",
        )
        exit_policy = entry_policy if sell_count else "no_sell_order_today"
        return {
            "buy_count": buy_count,
            "sell_count": sell_count,
            "hold_count": hold_count,
            "skip_count": skip_count,
            "abnormal_orders": abnormal_orders,
            "abnormal_fills": abnormal_fills,
            "entry_policy": entry_policy or "not_available",
            "exit_policy": exit_policy or "not_available",
        }

    def _build_checks(
        self,
        *,
        waterline: list[dict[str, Any]],
        production_campaigns: list[dict[str, Any]],
        campaign_reports: list[dict[str, Any]],
        artifact_index: list[dict[str, Any]],
        used_date_guard: dict[str, Any],
    ) -> list[dict[str, Any]]:
        checks: list[dict[str, Any]] = []
        failed_critical = [row for row in waterline if row.get("critical") and row.get("status") == "FAIL"]
        warn_waterline = [row for row in waterline if row.get("status") == "WARN"]
        checks.append({
            "check_name": "critical_waterline_ready",
            "status": "PASS" if not failed_critical else "FAIL",
            "reason": "all_critical_waterlines_ready" if not failed_critical else ",".join(str(x.get("table_name")) for x in failed_critical),
        })
        checks.append({
            "check_name": "noncritical_waterline_warning",
            "status": "PASS" if not warn_waterline else "WARN",
            "reason": "no_noncritical_warning" if not warn_waterline else ",".join(str(x.get("table_name")) for x in warn_waterline),
        })
        checks.append({
            "check_name": "active_production_campaign_exists",
            "status": "PASS" if production_campaigns else "FAIL",
            "reason": f"production_campaign_count={len(production_campaigns)}",
        })
        failed_campaigns = [row for row in campaign_reports if row.get("status") == "FAIL"]
        warn_campaigns = [row for row in campaign_reports if row.get("status") == "WARN"]
        checks.append({
            "check_name": "production_campaign_observable",
            "status": "PASS" if not failed_campaigns and not warn_campaigns else ("FAIL" if failed_campaigns else "WARN"),
            "reason": f"pass={len([x for x in campaign_reports if x.get('status') == 'PASS'])},warn={len(warn_campaigns)},fail={len(failed_campaigns)}",
        })
        checks.append({
            "check_name": "production_artifacts_present",
            "status": "PASS" if artifact_index else "WARN",
            "reason": f"artifact_count={len(artifact_index)}",
        })
        checks.append({
            "check_name": "future_data_guard",
            "status": used_date_guard.get("future_data_guard_status") or "WARN",
            "reason": used_date_guard.get("future_data_guard_reason") or "not_checked",
        })
        return checks

    @staticmethod
    def _derive_overall_status(checks: list[dict[str, Any]]) -> str:
        statuses = [str(check.get("status") or "WARN") for check in checks]
        if any(status == "FAIL" for status in statuses):
            return "FAIL"
        if any(status == "WARN" for status in statuses):
            return "WARN"
        return "PASS"

    @classmethod
    def _build_observation_notes(
        cls,
        *,
        overall_status: str,
        waterline: list[dict[str, Any]],
        market_context: dict[str, Any],
        campaign_reports: list[dict[str, Any]],
        artifact_index: list[dict[str, Any]],
    ) -> list[str]:
        notes = [
            "本报告是 production_daily_observation_report，不是 research report，也不是 M8 full ops report。",
            f"overall_status={overall_status}。",
        ]
        warn_or_fail = [row for row in waterline if row.get("status") != "PASS"]
        if warn_or_fail:
            notes.append("存在水位 WARN/FAIL，需优先检查：" + ", ".join(str(x.get("table_name")) for x in warn_or_fail[:10]))
        market_status = (market_context or {}).get("status")
        notes.append(f"market_context_status={market_status}。")
        for note in (market_context or {}).get("summary") or []:
            notes.append(str(note))
        for campaign in campaign_reports:
            notes.append(
                f"campaign={campaign.get('campaign_code')} portfolio_id={campaign.get('portfolio_id')} status={campaign.get('status')} reason={campaign.get('reason')}"
            )
            runtime = campaign.get("runtime_observation") or {}
            if runtime:
                notes.append(
                    f"campaign={campaign.get('campaign_code')} runtime_action={runtime.get('runtime_action')} campaign_data_status={runtime.get('campaign_data_status')} latest_campaign_date={runtime.get('latest_campaign_date')}"
                )
            risk = campaign.get("risk_metrics") or {}
            if risk:
                notes.append(
                    f"campaign={campaign.get('campaign_code')} max_position_weight={cls._fmt_percent(risk.get('max_position_weight'), 2)} stock_exposure={cls._fmt_percent(risk.get('stock_exposure'), 2)} total_position_pnl={cls._fmt_money(risk.get('total_position_pnl'))}"
                )
            losers = campaign.get("top_losers") or []
            if losers:
                worst = losers[0]
                code = worst.get("instrument_code") or worst.get("symbol") or worst.get("instrument_id")
                notes.append(
                    f"campaign={campaign.get('campaign_code')} worst_holding={code} total_pnl={cls._fmt_money(worst.get('total_pnl'))}"
                )
        if not artifact_index:
            notes.append("未发现相关 M6.5/M8 产物索引，需检查 daily run 是否生成报告产物。")
        return notes


    def _render_daily_control_panel(self, control_panel: dict[str, Any]) -> list[str]:
        if not control_panel:
            return ["## 0.0 生产晨间操作台 / Morning Control Panel", "", "- status: `WARN` / reason: `missing_control_panel`"]
        counts = control_panel.get("priority_counts") or {}
        top_action = control_panel.get("top_action") or {}
        action_text = (
            f"{top_action.get('priority')} / {top_action.get('item')}: {top_action.get('suggested_action')}"
            if top_action else "暂无 P0/P1 处理项，按 P2 观察项复核。"
        )
        return [
            "## 0.0 生产晨间操作台 / Morning Control Panel",
            "",
            f"- status: `{control_panel.get('status')}` / action_required: `{control_panel.get('action_required')}`",
            f"- top_action: {self._md_cell(action_text)}",
            "",
            "| field | value |",
            "|---|---|",
            f"| report_date | `{self._json_default(control_panel.get('report_date'))}` |",
            f"| signal_as_of_date | `{self._json_default(control_panel.get('signal_as_of_date'))}` |",
            f"| next_trade_date | `{self._json_default(control_panel.get('next_trade_date'))}` |",
            f"| overall_status | `{control_panel.get('overall_status')}` |",
            f"| next_trade_plan | `{control_panel.get('next_trade_plan_status')}` / `{control_panel.get('next_trade_plan_basis')}` |",
            f"| report_self_check | `{control_panel.get('report_self_check_status')}` |",
            f"| artifact_integrity | `{control_panel.get('artifact_integrity_status')}` |",
            f"| daily_diff | `{control_panel.get('daily_diff_status')}` |",
            f"| buy_price_quality | `{control_panel.get('buy_price_quality_status')}` |",
            f"| market_breadth_state | `{control_panel.get('market_breadth_state')}` |",
            f"| cash_ratio | `{self._fmt_percent(control_panel.get('cash_ratio'), 2) or 'UNKNOWN'}` |",
            f"| stock_exposure | `{self._fmt_percent(control_panel.get('stock_exposure'), 2) or 'UNKNOWN'}` |",
            f"| priority_counts | `P0={counts.get('P0', 0)}, P1={counts.get('P1', 0)}, P2={counts.get('P2', 0)}, INFO={counts.get('INFO', 0)}` |",
        ]

    def _render_action_priority(self, action_priority: dict[str, Any]) -> list[str]:
        lines = [
            "",
            "## 0.4 生产动作优先级 / Action Priority",
            "",
            f"- status: `{action_priority.get('status')}` / reason: `{action_priority.get('reason')}`",
            "",
            "| priority | status | item | reason | suggested_action |",
            "|---|---|---|---|---|",
        ]
        rows = action_priority.get("rows") or []
        if not rows:
            lines.append("| INFO | PASS | no_action | 未生成处理优先级 | 检查 report_self_check。 |")
            return lines
        priority_order = {"P0": 0, "P1": 1, "P2": 2, "INFO": 3}
        for row in sorted(rows, key=lambda item: priority_order.get(str(item.get("priority")), 9))[:20]:
            lines.append(
                "| "
                f"{self._md_cell(row.get('priority'))} | "
                f"{self._md_cell(row.get('status'))} | "
                f"{self._md_cell(row.get('item'))} | "
                f"{self._md_cell(row.get('reason'))} | "
                f"{self._md_cell(row.get('suggested_action'))} |"
            )
        return lines

    def _render_next_trade_plan_sla(self, sla: dict[str, Any]) -> list[str]:
        return [
            "",
            "## 0.5 次日计划生成 SLA / Next Trade Plan SLA",
            "",
            f"- status: `{sla.get('status')}` / reason: `{sla.get('reason')}` / blocker: `{sla.get('blocker')}`",
            "",
            "| field | value |",
            "|---|---|",
            f"| next_trade_date | `{self._json_default(sla.get('next_trade_date'))}` |",
            f"| plan_basis | `{sla.get('plan_basis')}` |",
            f"| expected_time | {self._md_cell(sla.get('expected_time'))} |",
            f"| materialized_at | `{self._json_default(sla.get('materialized_at'))}` |",
            f"| next_check_command | `{self._md_cell(sla.get('next_check_command'))}` |",
            f"| note | {self._md_cell(sla.get('note'))} |",
        ]

    def _render_report_self_check(self, self_check: dict[str, Any]) -> list[str]:
        lines = [
            "",
            "## 0.6 报告自身质量检查 / Report Self Check",
            "",
            f"- status: `{self_check.get('status')}` / reason: `{self_check.get('reason')}`",
            "",
            "| check | status | reason |",
            "|---|---|---|",
        ]
        for row in (self_check.get("rows") or [])[:20]:
            lines.append(f"| {self._md_cell(row.get('check_name'))} | {self._md_cell(row.get('status'))} | {self._md_cell(row.get('reason'))} |")
        return lines

    def _render_artifact_integrity(self, artifact_integrity: dict[str, Any]) -> list[str]:
        lines = [
            "",
            "## 0.7 产物完整性检查 / Artifact Integrity",
            "",
            f"- status: `{artifact_integrity.get('status')}` / reason: `{artifact_integrity.get('reason')}`",
            "",
            "| campaign | type | path | exists | size_bytes | modified_at | parse_status | status | reason |",
            "|---|---|---|---|---:|---|---|---|---|",
        ]
        for row in (artifact_integrity.get("rows") or [])[:25]:
            lines.append(
                "| "
                f"{self._md_cell(row.get('campaign_code'))} | "
                f"{self._md_cell(row.get('artifact_type'))} | "
                f"`{self._md_cell(row.get('path'))}` | "
                f"{row.get('exists')} | "
                f"{row.get('size_bytes')} | "
                f"{self._json_default(row.get('modified_at'))} | "
                f"{self._md_cell(row.get('parse_status'))} | "
                f"{self._md_cell(row.get('status'))} | "
                f"{self._md_cell(row.get('reason'))} |"
            )
        return lines

    def _render_daily_diff(self, daily_diff: dict[str, Any]) -> list[str]:
        lines = [
            "",
            "## 0.8 昨日对比 / Daily Diff",
            "",
            f"- status: `{daily_diff.get('status')}` / reason: `{self._md_cell(daily_diff.get('reason'))}`",
            f"- previous_report_date: `{self._json_default(daily_diff.get('previous_report_date'))}` / previous_report_path: `{self._md_cell(daily_diff.get('previous_report_path'))}`",
        ]
        summary = daily_diff.get("summary") or []
        if summary:
            lines.append("- summary: " + "; ".join(self._md_cell(item) for item in summary))
        lines.extend([
            "",
            "| metric | current | previous | delta / overlap | status | reason |",
            "|---|---:|---:|---:|---|---|",
        ])
        rows = daily_diff.get("rows") or []
        if not rows:
            lines.append("| previous_report | None | None | None | WARN | previous_report_not_found_or_not_parseable |")
            return lines
        for row in rows[:30]:
            lines.append(
                "| "
                f"{self._md_cell(row.get('metric'))} | "
                f"{self._format_diff_value(row.get('current_value'))} | "
                f"{self._format_diff_value(row.get('previous_value'))} | "
                f"{self._format_diff_value(row.get('delta'))} | "
                f"{self._md_cell(row.get('status'))} | "
                f"{self._md_cell(row.get('reason'))} |"
            )
        return lines

    def _render_buy_price_quality(self, buy_price_quality: dict[str, Any]) -> list[str]:
        lines = [
            "",
            "## 0.9 买入价格质量 / NEXT_OPEN Gap Quality",
            "",
            f"- status: `{buy_price_quality.get('status')}` / reason: `{self._md_cell(buy_price_quality.get('reason'))}`",
            f"- scope: `{self._md_cell(buy_price_quality.get('scope'))}`",
            "",
            "| campaign | status | buy | computed | favorable | unfavorable | avg_gap | weighted_gap | estimated_gap_cost | reason |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
        campaigns = buy_price_quality.get("campaigns") or []
        if not campaigns:
            lines.append("| None | WARN | 0 | 0 | 0 | 0 |  |  |  | no_campaign_quality_rows |")
            return lines
        for row in campaigns:
            lines.append(
                "| "
                f"{self._md_cell(row.get('campaign_code'))} | "
                f"{self._md_cell(row.get('status'))} | "
                f"{row.get('buy_order_count')} | "
                f"{row.get('computed_count')} | "
                f"{row.get('favorable_gap_count')} | "
                f"{row.get('unfavorable_gap_count')} | "
                f"{self._fmt_percent(row.get('avg_gap_ratio'), 2)} | "
                f"{self._fmt_percent(row.get('weighted_gap_ratio'), 2)} | "
                f"{self._fmt_money(row.get('estimated_gap_cost'))} | "
                f"{self._md_cell(row.get('reason'))} |"
            )
            worst_rows = row.get("worst_gap_top") or []
            best_rows = row.get("best_gap_top") or []
            if worst_rows:
                lines.extend([
                    "",
                    f"### 0.9 Campaign: {self._md_cell(row.get('campaign_code'))} 不利跳空 Top",
                    "",
                    "| rank | code | name | estimated_price | fill_price | qty | gap | gap_ratio | estimated_gap_cost |",
                    "|---:|---|---|---:|---:|---:|---:|---:|---:|",
                ])
                for detail in worst_rows[:5]:
                    lines.append(
                        "| "
                        f"{detail.get('rank_no')} | "
                        f"{self._md_cell(detail.get('instrument_code') or detail.get('symbol'))} | "
                        f"{self._md_cell(detail.get('display_name'))} | "
                        f"{self._fmt_decimal(detail.get('estimated_price'), 4)} | "
                        f"{self._fmt_decimal(detail.get('fill_price'), 4)} | "
                        f"{self._fmt_quantity(detail.get('quantity'))} | "
                        f"{self._fmt_decimal(detail.get('gap_amount'), 4)} | "
                        f"{self._fmt_percent(detail.get('gap_ratio'), 2)} | "
                        f"{self._fmt_money(detail.get('estimated_gap_cost'))} |"
                    )
            if best_rows:
                lines.extend([
                    "",
                    f"### 0.9 Campaign: {self._md_cell(row.get('campaign_code'))} 有利跳空 Top",
                    "",
                    "| rank | code | name | estimated_price | fill_price | qty | gap | gap_ratio | estimated_gap_cost |",
                    "|---:|---|---|---:|---:|---:|---:|---:|---:|",
                ])
                for detail in best_rows[:5]:
                    lines.append(
                        "| "
                        f"{detail.get('rank_no')} | "
                        f"{self._md_cell(detail.get('instrument_code') or detail.get('symbol'))} | "
                        f"{self._md_cell(detail.get('display_name'))} | "
                        f"{self._fmt_decimal(detail.get('estimated_price'), 4)} | "
                        f"{self._fmt_decimal(detail.get('fill_price'), 4)} | "
                        f"{self._fmt_quantity(detail.get('quantity'))} | "
                        f"{self._fmt_decimal(detail.get('gap_amount'), 4)} | "
                        f"{self._fmt_percent(detail.get('gap_ratio'), 2)} | "
                        f"{self._fmt_money(detail.get('estimated_gap_cost'))} |"
                    )
        return lines

    @classmethod
    def _format_diff_value(cls, value: Any) -> str:
        if value is None or value == "":
            return ""
        if isinstance(value, bool):
            return str(value)
        if isinstance(value, int):
            return f"{value:,}"
        if isinstance(value, Decimal):
            return cls._fmt_decimal(value, 6)
        value_decimal = cls._to_decimal_value(value)
        if value_decimal is not None:
            return cls._fmt_decimal(value_decimal, 6)
        return cls._md_cell(value)

    def _render_manual_review_checklist(self, checklist: list[dict[str, Any]]) -> list[str]:
        lines = ["", "## 6.1 今日人工复盘清单 / Manual Review Checklist", ""]
        if not checklist:
            lines.append("- [ ] 未生成复盘清单，请检查 report_self_check。")
            return lines
        for item in checklist:
            checked = "x" if item.get("checked") else " "
            lines.append(
                f"- [{checked}] `{self._md_cell(item.get('priority'))}` {self._md_cell(item.get('item'))} —— {self._md_cell(item.get('reason'))}"
            )
        return lines

    def _render_next_trade_plan(self, next_trade_plan: dict[str, Any]) -> list[str]:
        if not next_trade_plan:
            return [
                "",
                "## 0.3 次日交易计划 / Next Trading Day Plan",
                "",
                "- status: `WARN` / reason: `missing_next_trade_plan`",
                "",
            ]

        lines: list[str] = [
            "",
            "## 0.3 次日交易计划 / Next Trading Day Plan",
            "",
            f"- scope: `{next_trade_plan.get('scope')}`",
            f"- status: `{next_trade_plan.get('status')}` / reason: `{next_trade_plan.get('reason')}`",
            f"- report_date: `{self._json_default(next_trade_plan.get('report_date'))}` / signal_as_of_date: `{self._json_default(next_trade_plan.get('signal_as_of_date'))}` / next_trade_date: `{self._json_default(next_trade_plan.get('next_trade_date'))}`",
            f"- note: {next_trade_plan.get('note')}",
            "",
            "| campaign | status | plan_basis | target_run_id | order_run_id | planned_buy | planned_sell | planned_hold | review | reason |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---|",
        ]
        for plan in next_trade_plan.get("campaigns") or []:
            lines.append(
                "| "
                f"{self._md_cell(plan.get('campaign_code'))} | "
                f"{self._md_cell(plan.get('status'))} | "
                f"{self._md_cell(plan.get('plan_basis'))} | "
                f"{plan.get('target_run_id')} | "
                f"{plan.get('order_run_id')} | "
                f"{plan.get('planned_buy_count')} | "
                f"{plan.get('planned_sell_count')} | "
                f"{plan.get('planned_hold_count')} | "
                f"{plan.get('planned_review_count')} | "
                f"{self._md_cell(plan.get('reason'))} |"
            )

        for plan in next_trade_plan.get("campaigns") or []:
            campaign_code = plan.get("campaign_code") or "unknown_campaign"
            lines.extend([
                "",
                f"### 0.3 Campaign: {campaign_code}",
                "",
                f"- strategy: `{plan.get('strategy_code')}` / `{plan.get('strategy_version_code')}`",
                f"- portfolio_id: `{plan.get('portfolio_id')}` / current_position_run_id: `{plan.get('current_position_run_id')}`",
                f"- plan_basis: `{plan.get('plan_basis')}`",
                "",
                "#### 明日计划买入 / 加仓",
                "",
            ])
            lines.extend(
                self._render_next_trade_plan_action_rows(
                    rows=plan.get("planned_buy_rows") or [],
                    empty_note="未观察到 next_trade_date 的 BUY order 或目标加仓候选。",
                )
            )
            lines.extend([
                "",
                "#### 明日计划卖出 / 减仓",
                "",
            ])
            lines.extend(
                self._render_next_trade_plan_action_rows(
                    rows=plan.get("planned_sell_rows") or [],
                    empty_note="未观察到 next_trade_date 的 SELL order 或减仓/退出候选；若正式卖点规则尚未落表，不能解释为卖点未触发。",
                )
            )
            lines.extend([
                "",
                "#### 明日继续持有 / 观察",
                "",
            ])
            hold_rows = plan.get("planned_hold_rows") or []
            review_rows = plan.get("current_position_review_rows") or []
            if hold_rows:
                lines.extend(
                    self._render_next_trade_plan_action_rows(
                        rows=hold_rows,
                        empty_note="未观察到 next_trade_date 的 HOLD target。",
                    )
                )
            elif review_rows:
                lines.extend([
                    "- 当前尚未观察到 next_trade_date target/order，下面仅列出当前持仓，供下一次计划生成后复核；不是正式持有建议。",
                    "",
                    "| code | name | quantity | weight | market_value | total_pnl | status | reason |",
                    "|---|---|---:|---:|---:|---:|---|---|",
                ])
                for row in review_rows[:15]:
                    code = row.get("instrument_code") or row.get("symbol") or row.get("instrument_id")
                    lines.append(
                        "| "
                        f"{self._md_cell(code)} | "
                        f"{self._md_cell(row.get('display_name'))} | "
                        f"{self._fmt_quantity(row.get('quantity'))} | "
                        f"{self._fmt_percent(row.get('position_weight'), 2)} | "
                        f"{self._fmt_money(row.get('market_value'))} | "
                        f"{self._fmt_money(row.get('total_pnl'))} | "
                        f"{self._md_cell(row.get('position_status'))} | "
                        "pending_next_trade_plan_materialization |"
                    )
            else:
                lines.append("- 未观察到 next_trade_date 的 HOLD target，且没有可展示的当前持仓复核列表。")
            lines.append("")
        return lines

    def _render_next_trade_plan_action_rows(self, *, rows: list[dict[str, Any]], empty_note: str) -> list[str]:
        if not rows:
            return [f"- {empty_note}"]
        lines = [
            "| action | code | name | rank | target_weight | current_qty | target_qty | order_qty | price_or_policy | status | reason |",
            "|---|---|---|---:|---:|---:|---:|---:|---|---|---|",
        ]
        for row in rows[:30]:
            code = row.get("instrument_code") or row.get("symbol") or row.get("instrument_id")
            action = row.get("plan_action") or row.get("order_side") or "OBSERVE"
            price_or_policy = self._dedupe_join(
                [
                    row.get("price_fill_rule"),
                    f"estimated_price={self._fmt_money(row.get('estimated_price'))}" if row.get("estimated_price") is not None else None,
                    row.get("plan_reason"),
                ],
                separator="; ",
            )
            reason = self._dedupe_join(
                [
                    row.get("target_reason_code"),
                    row.get("signal_reason_code"),
                    row.get("target_status_reason"),
                    row.get("reject_reason"),
                    row.get("plan_reason"),
                ],
                separator="; ",
            )
            status = row.get("order_status") or row.get("current_position_status") or "TARGET_OBSERVED"
            lines.append(
                "| "
                f"{self._md_cell(action)} | "
                f"{self._md_cell(code)} | "
                f"{self._md_cell(row.get('display_name'))} | "
                f"{row.get('rank_no') or ''} | "
                f"{self._fmt_percent(row.get('target_weight'), 2)} | "
                f"{self._fmt_quantity(row.get('current_quantity'))} | "
                f"{self._fmt_quantity(row.get('target_quantity'))} | "
                f"{self._fmt_quantity(row.get('order_quantity'))} | "
                f"{self._md_cell(price_or_policy)} | "
                f"{self._md_cell(status)} | "
                f"{self._md_cell(reason)} |"
            )
        return lines

    def _render_strategy_trade_decision_explanation(
        self,
        campaign: dict[str, Any],
        trade_explain: dict[str, Any],
    ) -> list[str]:
        """Render a production-observation answer to: which strategy selected, did it enter, and which names hit buy/sell/hold/skip.

        This is deliberately not a formal independent buy/sell signal engine. It explains the
        observed production paper-campaign decision chain: strategy selection -> target -> order -> fill -> position.
        """
        selection = campaign.get("selection_summary") or {}
        selected_rows = campaign.get("selected_instruments") or []
        trade_rows = campaign.get("trade_details") or []
        position_rows = campaign.get("positions_preview") or []
        runtime = campaign.get("runtime_observation") or {}
        lifecycle = campaign.get("trade_lifecycle") or {}

        buy_rows = [row for row in trade_rows if str(row.get("order_side") or "").upper() == "BUY"]
        sell_rows = [row for row in trade_rows if str(row.get("order_side") or "").upper() == "SELL"]
        ordered_ids = {row.get("instrument_id") for row in trade_rows if row.get("instrument_id") is not None}
        skip_rows = [row for row in selected_rows if row.get("instrument_id") not in ordered_ids]
        hold_rows = [row for row in position_rows if str(row.get("position_status") or "").upper() == "OPEN"]

        route_names = self._dedupe_strings(
            [
                row.get("target_reason_code") or row.get("signal_reason_code")
                for row in selected_rows[:30]
            ]
        )
        strategy_line = (
            f"今日使用 `{campaign.get('strategy_code')}` / `{campaign.get('strategy_version_code')}`，"
            f"在 `{self._dedupe_join(route_names[:3]) or 'not_available'}` 路由/原因下，"
            f"从 `{selection.get('candidate_count')}` 只候选股中选出 `{selection.get('selected_count')}` 只，"
            f"target_rank_range=`{selection.get('min_target_rank')}`-`{selection.get('max_target_rank')}`，"
            f"score_range=`{self._fmt_decimal(selection.get('min_target_score'), 4)}`-`{self._fmt_decimal(selection.get('max_target_score'), 4)}`。"
        )
        buy_status = "BUY_EXECUTED" if buy_rows else "NO_BUY_EXECUTED"
        sell_status = "SELL_EXECUTED" if sell_rows else "NO_SELL_ORDER_OBSERVED"
        entry_policy = trade_explain.get("entry_policy") or "not_available"
        exit_policy = trade_explain.get("exit_policy") or "not_available"

        lines: list[str] = [
            "#### 策略选股与买卖点解释",
            "",
            f"- scope: `production_strategy_trade_decision_observation_not_independent_buy_sell_engine`",
            f"- 问题1_用什么策略选: {strategy_line}",
            f"- 问题2_到买点了吗: `{buy_status}`；当前定义为生产模拟入场执行条件，即策略入选 + target 生成 + BUY order + NEXT_OPEN/CORE_DAILY_BAR_OPEN 成交，不等同于独立技术买点信号。",
            f"- 问题3_当天买卖点股票: BUY_EXECUTED=`{len(buy_rows)}` / SELL_EXECUTED=`{len(sell_rows)}` / HOLD_OBSERVED=`{len(hold_rows)}` / SKIP=`{len(skip_rows)}`。",
            f"- entry_policy: `{entry_policy}` / exit_policy: `{exit_policy}` / lifecycle_context: `{lifecycle.get('lifecycle_context') or runtime.get('runtime_action')}`",
            "",
            "##### 今日达到买入执行条件的股票",
            "",
        ]
        if not buy_rows:
            lines.extend(["- 当日无 BUY order / fill 记录。", ""])
        else:
            lines.extend([
                "| rank | code | name | target_weight | order_qty | fill_qty | fill_price | entry_policy | strategy_reason | execution_reason |",
                "|---:|---|---|---:|---:|---:|---:|---|---|---|",
            ])
            for row in buy_rows[:30]:
                code = row.get("instrument_code") or row.get("symbol") or row.get("instrument_id")
                reason_parts = row.get("trade_reason_parts") or {}
                strategy_reason = reason_parts.get("strategy_reason") or row.get("target_reason_code") or row.get("signal_reason_code")
                execution_reason = self._dedupe_join(
                    [
                        reason_parts.get("sizing_reason"),
                        reason_parts.get("price_reason"),
                        reason_parts.get("fill_reason"),
                    ],
                    separator="; ",
                )
                lines.append(
                    "| "
                    f"{row.get('rank_no') or ''} | "
                    f"{self._md_cell(code)} | "
                    f"{self._md_cell(row.get('display_name'))} | "
                    f"{self._fmt_percent(row.get('target_weight'), 2)} | "
                    f"{self._fmt_quantity(row.get('order_quantity'))} | "
                    f"{self._fmt_quantity(row.get('fill_quantity'))} | "
                    f"{self._fmt_money(row.get('fill_price'))} | "
                    f"{self._md_cell(row.get('entry_policy'))} | "
                    f"{self._md_cell(strategy_reason)} | "
                    f"{self._md_cell(execution_reason)} |"
                )
            lines.append("")

        lines.extend([
            "##### 今日达到卖出执行条件的股票",
            "",
        ])
        if not sell_rows:
            lines.extend([
                "- 当日无 SELL order。当前报告只能观察到已发生卖出订单；正式卖点规则（20 交易日退出、利润回撤、止损、卖出信号）尚未落表，因此不硬判定触发/未触发。",
                "",
            ])
        else:
            lines.extend([
                "| code | name | target_weight | order_qty | fill_qty | fill_price | exit_policy | sell_reason | execution_reason |",
                "|---|---|---:|---:|---:|---:|---|---|---|",
            ])
            for row in sell_rows[:30]:
                code = row.get("instrument_code") or row.get("symbol") or row.get("instrument_id")
                reason_parts = row.get("trade_reason_parts") or {}
                sell_reason = reason_parts.get("strategy_reason") or row.get("target_reason_code") or row.get("signal_reason_code")
                execution_reason = self._dedupe_join(
                    [reason_parts.get("sizing_reason"), reason_parts.get("price_reason"), reason_parts.get("fill_reason")],
                    separator="; ",
                )
                lines.append(
                    "| "
                    f"{self._md_cell(code)} | {self._md_cell(row.get('display_name'))} | "
                    f"{self._fmt_percent(row.get('target_weight'), 2)} | {self._fmt_quantity(row.get('order_quantity'))} | "
                    f"{self._fmt_quantity(row.get('fill_quantity'))} | {self._fmt_money(row.get('fill_price'))} | "
                    f"{self._md_cell(row.get('exit_policy'))} | {self._md_cell(sell_reason)} | {self._md_cell(execution_reason)} |"
                )
            lines.append("")

        lines.extend([
            "##### 今日继续持有的股票观察",
            "",
            "- HOLD_OBSERVED 表示收盘后 position_status=OPEN，可能与当日 BUY_EXECUTED 重叠；它解释的是为什么继续纳入持仓观察，不代表正式卖点规则未触发。",
        ])
        if hold_rows:
            lines.extend([
                "",
                "| code | name | weight | total_pnl | status | hold_reason |",
                "|---|---|---:|---:|---|---|",
            ])
            for row in hold_rows[:15]:
                code = row.get("instrument_code") or row.get("symbol") or row.get("instrument_id")
                lines.append(
                    "| "
                    f"{self._md_cell(code)} | {self._md_cell(row.get('display_name'))} | "
                    f"{self._fmt_percent(row.get('position_weight'), 2)} | {self._fmt_money(row.get('total_pnl'))} | "
                    f"{self._md_cell(row.get('position_status'))} | position_status=OPEN; no_sell_order_observed |"
                )
        else:
            lines.append("- 当前没有 OPEN 持仓。")
        lines.append("")

        lines.extend([
            "##### 今日跳过 / 未成交 / 异常股票",
            "",
        ])
        if not skip_rows:
            lines.extend(["- SKIP=0；当日目标均进入订单/成交链路，未观察到目标生成后跳过。", ""])
        else:
            lines.extend([
                "| rank | code | name | target_weight | skip_reason |",
                "|---:|---|---|---:|---|",
            ])
            for row in skip_rows[:30]:
                code = row.get("instrument_code") or row.get("symbol") or row.get("instrument_id")
                lines.append(
                    f"| {row.get('rank_no') or ''} | {self._md_cell(code)} | {self._md_cell(row.get('display_name'))} | {self._fmt_percent(row.get('target_weight'), 2)} | target_without_order_or_rejected |"
                )
            lines.append("")
        return lines

    def _render_trade_lifecycle_observation(self, lifecycle: dict[str, Any]) -> list[str]:
        if not lifecycle:
            return [
                "#### 买卖点生命周期观察",
                "",
                "- status: `WARN` / reason: `missing_lifecycle_context`",
                "",
            ]
        lines: list[str] = [
            "#### 买卖点生命周期观察",
            "",
            f"- scope: `{lifecycle.get('scope')}`",
            f"- lifecycle_context: `{lifecycle.get('lifecycle_context')}`",
            f"- target_run_id: `{lifecycle.get('target_run_id')}` / order_run_id: `{lifecycle.get('order_run_id')}` / fill_run_id: `{lifecycle.get('fill_run_id')}` / position_run_id: `{lifecycle.get('position_run_id')}`",
            f"- buy_count: `{lifecycle.get('buy_count')}` / sell_count: `{lifecycle.get('sell_count')}` / current_position_count: `{lifecycle.get('current_position_count')}` / no_exit_count: `{lifecycle.get('no_exit_count')}`",
            f"- calendar_holding_days_candidate: min=`{lifecycle.get('calendar_holding_days_min')}` / max=`{lifecycle.get('calendar_holding_days_max')}` / near_20=`{lifecycle.get('near_20_calendar_day_count')}` / reached_20=`{lifecycle.get('reached_20_calendar_day_count')}`",
            "- note: 当前为生产观察版生命周期骨架；未落表的 20 交易日退出、利润回撤、止损、卖出信号不做硬判定。",
            "",
            "| lifecycle_check | status | value | reason |",
            "|---|---|---|---|",
        ]
        for check in lifecycle.get("exit_checks") or []:
            lines.append(f"| {check.get('check_name')} | {check.get('status')} | {check.get('value')} | {check.get('reason')} |")
        lines.extend([
            "",
            "##### 持仓生命周期候选 Top",
            "",
            "| code | name | first_position_date | position_date | calendar_holding_days_candidate | days_to_20_candidate | total_pnl | last_order_side | status |",
            "|---|---|---:|---:|---:|---:|---:|---|---|",
        ])
        for item in (lifecycle.get("details") or [])[:10]:
            code = item.get("instrument_code") or item.get("symbol") or item.get("instrument_id")
            lines.append(
                f"| {code} | {item.get('display_name')} | {self._json_default(item.get('first_position_date'))} | {self._json_default(item.get('position_date'))} | {item.get('calendar_holding_days_candidate')} | {item.get('calendar_days_to_20_candidate')} | {self._fmt_money(item.get('total_pnl'))} | {item.get('last_order_side')} | {item.get('position_status')} |"
            )
        lines.append("")
        return lines

    def _render_markdown(self, payload: dict[str, Any]) -> str:
        lines: list[str] = []
        return_attribution_by_campaign = {
            str(item.get("campaign_code") or ""): item
            for item in (payload.get("return_attribution") or [])
        }
        lines.extend([
            "# Production Daily Observation Report",
            "",
            "> 这是一份生产端 daily run 观察报告，不是研究报告，不是 M8 full ops 报告，也不是正式实盘交易报告。",
            "",
            *self._render_daily_control_panel(payload.get("daily_control_panel") or {}),
            "",
            "## 0. 今日运行概览",
            "",
            "| field | value |",
            "|---|---|",
            f"| report_date | `{self._json_default(payload.get('report_date'))}` |",
            f"| generated_at | `{payload.get('generated_at')}` |",
            f"| execution_context | `{payload.get('execution_context')}` |",
            f"| report_context | `{payload.get('report_context')}` |",
            f"| daily_profile | `{payload.get('daily_profile')}` |",
            f"| git_commit | `{payload.get('git_commit')}` |",
            f"| git_branch | `{payload.get('git_branch')}` |",
            f"| git_dirty | `{payload.get('git_dirty')}` |",
            f"| git_commit_status | `{payload.get('git_commit_status')}` |",
            f"| docker_container | `{payload.get('docker_container')}` |",
            f"| docker_image_id | `{payload.get('docker_image_id')}` |",
            f"| docker_image_digest | `{payload.get('docker_image_digest')}` |",
            f"| container_started_at | `{payload.get('container_started_at')}` |",
            f"| runtime_command | `{self._md_cell(payload.get('runtime_command'))}` |",
            f"| database | `{payload.get('database')}` |",
            f"| paper_campaign_context | `{payload.get('paper_campaign_context')}` |",
            f"| signal_as_of_date | `{self._json_default(payload.get('signal_as_of_date'))}` |",
            f"| overall_status | `{payload.get('overall_status')}` |",
            "",
            "## 0.1 今日结论",
            "",
            "| item | status | summary |",
            "|---|---|---|",
        ])
        for row in payload.get("daily_conclusion") or []:
            lines.append(
                f"| {self._md_cell(row.get('item'))} | {self._md_cell(row.get('status'))} | {self._md_cell(row.get('summary'))} |"
            )

        used_guard = payload.get("used_date_guard") or {}
        lines.extend([
            "",
            "## 0.2 数据使用语义 / Future Data Guard",
            "",
            "| field | value |",
            "|---|---|",
            f"| latest_available_date | `{self._json_default(used_guard.get('latest_available_date'))}` |",
            f"| used_for_signal_date | `{self._json_default(used_guard.get('used_for_signal_date'))}` |",
            f"| used_for_trade_date | `{self._json_default(used_guard.get('used_for_trade_date'))}` |",
            f"| future_data_guard_status | `{used_guard.get('future_data_guard_status')}` |",
            f"| future_data_guard_reason | `{self._md_cell(used_guard.get('future_data_guard_reason'))}` |",
            "",
            "| check | used_date | expected_max_date | status | reason |",
            "|---|---:|---:|---|---|",
        ])
        for row in (used_guard.get("details") or [])[:20]:
            lines.append(
                f"| {self._md_cell(row.get('check_name'))} | {self._json_default(row.get('used_date'))} | {self._json_default(row.get('expected_max_date'))} | {row.get('status')} | {self._md_cell(row.get('reason'))} |"
            )

        lines.extend(self._render_next_trade_plan(payload.get("next_trade_plan") or {}))
        lines.extend(self._render_action_priority(payload.get("action_priority") or {}))
        lines.extend(self._render_next_trade_plan_sla(payload.get("next_trade_plan_sla") or {}))
        lines.extend(self._render_report_self_check(payload.get("report_self_check") or {}))
        lines.extend(self._render_artifact_integrity(payload.get("artifact_integrity") or {}))
        lines.extend(self._render_daily_diff(payload.get("daily_diff") or {}))
        lines.extend(self._render_buy_price_quality(payload.get("buy_price_quality") or {}))

        lines.extend([
            "",
            "## 1. 数据水位",
            "",
            "| table | basis | expected_date | max_date | rows | max_run_id | status | reason |",
            "|---|---|---:|---:|---:|---:|---|---|",
        ])
        for row in payload.get("waterline") or []:
            lines.append(
                f"| {row.get('table_name')} | {row.get('freshness_basis')} | {self._json_default(row.get('expected_date'))} | {self._json_default(row.get('max_date'))} | {row.get('rows')} | {row.get('max_run_id')} | {row.get('status')} | {row.get('reason')} |"
            )

        data_refresh = payload.get("data_refresh_summary") or {}
        lines.extend([
            "",
            "## 1.1 基础数据刷新报告",
            "",
            f"- status: `{data_refresh.get('status')}` / reason: `{data_refresh.get('reason')}`",
            "",
            "| refresh_module | provider | date_from | date_to | inserted | updated | skipped | failed | fallback | key_error | status |",
            "|---|---|---:|---:|---:|---:|---:|---:|---|---|---|",
        ])
        for refresh_row in (data_refresh.get("rows") or [])[:15]:
            lines.append(
                f"| {refresh_row.get('refresh_module')} | {refresh_row.get('provider')} | {self._json_default(refresh_row.get('date_from'))} | {self._json_default(refresh_row.get('date_to'))} | {refresh_row.get('inserted_rows')} | {refresh_row.get('updated_rows')} | {refresh_row.get('skipped_rows')} | {refresh_row.get('failed_rows')} | {refresh_row.get('provider_fallback')} | {refresh_row.get('key_error')} | {refresh_row.get('status')} |"
            )

        feature = payload.get("feature_readiness") or {}
        lines.extend([
            "",
            "## 1.2 特征 / 因子 / 指标准备情况",
            "",
            f"- feature_status: `{feature.get('feature_status')}` / reason: `{feature.get('reason')}`",
            "",
            "| feature_date | universe_size | valid_instrument_count | excluded_instrument_count | indicator_rows | factor_rows | missing_feature_count | feature_rows | factor_date | indicator_date |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            f"| {self._json_default(feature.get('feature_date'))} | {feature.get('universe_size')} | {feature.get('valid_instrument_count')} | {feature.get('excluded_instrument_count')} | {feature.get('indicator_rows')} | {feature.get('factor_rows')} | {feature.get('missing_feature_count')} | {feature.get('feature_rows')} | {self._json_default(feature.get('factor_date'))} | {self._json_default(feature.get('indicator_date'))} |",
        ])

        market_context = payload.get("market_context") or {}
        breadth = market_context.get("breadth") or {}
        lines.extend([
            "",
            "## 2. 市场环境观察",
            "",
            f"- market_context_status: `{market_context.get('status')}`",
            f"- market_breadth_state: `{breadth.get('market_breadth_state')}`",
            f"- total_rows: `{breadth.get('total_rows')}` / up: `{breadth.get('up_rows')}` / down: `{breadth.get('down_rows')}` / flat: `{breadth.get('flat_rows')}`",
            f"- up_ratio: `{self._fmt_percent(breadth.get('up_ratio'), 2)}` / down_ratio: `{self._fmt_percent(breadth.get('down_ratio'), 2)}`",
            f"- limit_up: `{breadth.get('limit_up_rows')}` / limit_down: `{breadth.get('limit_down_rows')}` / near_limit_up: `{breadth.get('near_limit_up_rows')}` / near_limit_down: `{breadth.get('near_limit_down_rows')}`",
            f"- avg_pct_change: `{self._fmt_percent(breadth.get('avg_pct_change'), 2)}` / median_pct_change: `{self._fmt_percent(breadth.get('median_pct_change'), 2)}` / total_amount: `{self._fmt_money(breadth.get('total_amount'))}`",
            "",
            "### 2.1 指数概况",
            "",
            "| index | close | pct_change | turnover |",
            "|---|---:|---:|---:|",
        ])
        for item in (market_context.get("index_overview") or [])[:12]:
            index_name = item.get("index_name") or item.get("index_code") or item.get("market_index_id")
            lines.append(f"| {index_name} | {self._fmt_money(item.get('close'))} | {self._fmt_percent(item.get('pct_change'), 2)} | {self._fmt_money(item.get('turnover'))} |")
        lines.extend([
            "",
            "### 2.2 强势股 Top",
            "",
            "| code | name | pct_change | close | amount | limit_up |",
            "|---|---|---:|---:|---:|---|",
        ])
        for item in (market_context.get("strong_stocks") or [])[:20]:
            code = item.get("instrument_code") or item.get("symbol") or item.get("instrument_id")
            lines.append(f"| {code} | {item.get('display_name')} | {self._fmt_percent(item.get('pct_change'), 2)} | {self._fmt_money(item.get('close'))} | {self._fmt_money(item.get('amount'))} | {item.get('is_limit_up')} |")
        lines.extend([
            "",
            "### 2.3 弱势股 Top",
            "",
            "| code | name | pct_change | close | amount | limit_down |",
            "|---|---|---:|---:|---:|---|",
        ])
        for item in (market_context.get("weak_stocks") or [])[:20]:
            code = item.get("instrument_code") or item.get("symbol") or item.get("instrument_id")
            lines.append(f"| {code} | {item.get('display_name')} | {self._fmt_percent(item.get('pct_change'), 2)} | {self._fmt_money(item.get('close'))} | {self._fmt_money(item.get('amount'))} | {item.get('is_limit_down')} |")
        lines.extend([
            "",
            "### 2.4 行业强弱",
            "",
            f"- status: `{(market_context.get('industry_strength') or {}).get('status')}` / reason: `{(market_context.get('industry_strength') or {}).get('reason')}`",
            "",
            "| industry | count | up | down | avg_pct_change | median_pct_change | limit_up | amount |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for item in ((market_context.get("industry_strength") or {}).get("rows") or [])[:15]:
            lines.append(f"| {item.get('tag_name')} | {item.get('instrument_count')} | {item.get('up_rows')} | {item.get('down_rows')} | {self._fmt_percent(item.get('avg_pct_change'), 2)} | {self._fmt_percent(item.get('median_pct_change'), 2)} | {item.get('limit_up_rows')} | {self._fmt_money(item.get('total_amount'))} |")
        lines.extend([
            "",
            "### 2.5 概念 / 题材数据状态",
            "",
            f"- status: `{(market_context.get('concept_strength') or {}).get('status')}` / reason: `{(market_context.get('concept_strength') or {}).get('reason')}`",
            "",
            "| concept | count | up | down | avg_pct_change | limit_up | amount |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ])
        for item in ((market_context.get("concept_strength") or {}).get("rows") or [])[:15]:
            lines.append(f"| {item.get('tag_name')} | {item.get('instrument_count')} | {item.get('up_rows')} | {item.get('down_rows')} | {self._fmt_percent(item.get('avg_pct_change'), 2)} | {item.get('limit_up_rows')} | {self._fmt_money(item.get('total_amount'))} |")
        lines.extend([
            "",
            "### 2.6 策略与市场匹配度",
            "",
            "| campaign | selected_count | selected_avg_return | selected_up | selected_down | selected_limit_up | holding_count | holding_avg_return | holding_up | holding_down |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for item in market_context.get("strategy_alignment") or []:
            selected = item.get("selected_market_stats") or {}
            holding = item.get("holding_market_stats") or {}
            lines.append(
                f"| {item.get('campaign_code')} | {selected.get('instrument_count')} | {self._fmt_percent(selected.get('avg_pct_change'), 2)} | {selected.get('up_rows')} | {selected.get('down_rows')} | {selected.get('limit_up_rows')} | {holding.get('instrument_count')} | {self._fmt_percent(holding.get('avg_pct_change'), 2)} | {holding.get('up_rows')} | {holding.get('down_rows')} |"
            )
        lines.extend([
            "",
            "### 2.7 策略 / 持仓行业与概念暴露",
            "",
            "| campaign | group | tag | selected_count | selected_weight | holding_count | holding_weight | holding_pnl | market_avg_return | market_limit_up | match_status |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
        ])
        for item in market_context.get("strategy_alignment") or []:
            campaign_code = item.get("campaign_code")
            for group_name, exposure_key in (("industry", "industry_exposure"), ("concept", "concept_exposure")):
                exposure = item.get(exposure_key) or {}
                for row in (exposure.get("rows") or [])[:12]:
                    lines.append(
                        f"| {campaign_code} | {group_name} | {row.get('tag_name')} | {row.get('selected_count')} | {self._fmt_percent(row.get('selected_weight'), 2)} | {row.get('holding_count')} | {self._fmt_percent(row.get('holding_weight'), 2)} | {self._fmt_money(row.get('holding_total_pnl'))} | {self._fmt_percent(row.get('market_avg_pct_change'), 2)} | {row.get('market_limit_up_rows')} | {row.get('match_status')} |"
                    )
        lines.extend([
            "",
            "### 2.8 策略与市场主线匹配小结",
            "",
            "| campaign | status | reason | strong_main_tags | weak_main_tags | generic_filtered | top_mainline_tag | top_mainline_match | filtered_top_generic |",
            "|---|---|---|---:|---:|---:|---|---|---|",
        ])
        for item in market_context.get("strategy_alignment") or []:
            summary = item.get("market_match_summary") or {}
            lines.append(
                f"| {item.get('campaign_code')} | {summary.get('status')} | {summary.get('reason')} | {summary.get('strong_tag_count')} | {summary.get('weak_tag_count')} | {summary.get('generic_tag_filtered_count')} | {summary.get('top_exposure_tag')} | {summary.get('top_exposure_match_status')} | {summary.get('top_generic_tag_filtered') or ''} |"
            )
        lines.extend(self._render_market_observation_conclusion(market_context))
        lines.extend(["", "## 3. Production Paper Campaigns", ""])
        for campaign in payload.get("campaigns") or []:
            snapshot = campaign.get("snapshot") or {}
            selection = campaign.get("selection_summary") or {}
            trade = campaign.get("trade_summary") or {}
            orders = trade.get("orders") if isinstance(trade, dict) else {}
            fills = trade.get("fills") if isinstance(trade, dict) else {}
            lines.extend([
                f"### {campaign.get('campaign_code')}",
                "",
                f"- status: `{campaign.get('status')}` / reason: `{campaign.get('reason')}`",
                f"- strategy: `{campaign.get('strategy_code')}` / `{campaign.get('strategy_version_code')}`",
                f"- portfolio_id: `{campaign.get('portfolio_id')}`",
                f"- validation_stage: `{campaign.get('validation_stage')}`",
                f"- target_run_id: `{selection.get('target_run_id')}`",
                f"- source_signal_run_id: `{selection.get('source_signal_run_id')}` / screen_request_id: `{selection.get('source_screen_request_id')}`",
                f"- candidate_count: `{selection.get('candidate_count')}` / selected_count: `{selection.get('selected_count')}`",
                f"- target_rank_range: `{selection.get('min_target_rank')}` - `{selection.get('max_target_rank')}` / source_rank_range: `{selection.get('min_source_rank')}` - `{selection.get('max_source_rank')}`",
                f"- score_range: `{self._fmt_decimal(selection.get('min_target_score'), 4)}` - `{self._fmt_decimal(selection.get('max_target_score'), 4)}` / rank_scope_check: `{selection.get('rank_scope_check')}`",
                f"- rank_out_of_scope_rows: `{selection.get('rank_out_of_scope_rows')}`",
                f"- order_run_id: `{(orders or {}).get('order_run_id')}` / order_count: `{(orders or {}).get('order_count')}` / buy: `{(orders or {}).get('buy_order_count')}` / sell: `{(orders or {}).get('sell_order_count')}`",
                f"- fill_run_id: `{(fills or {}).get('fill_run_id')}` / fill_count: `{(fills or {}).get('fill_count')}`",
                f"- snapshot_run_id: `{snapshot.get('snapshot_run_id')}` / position_run_id: `{snapshot.get('position_run_id') or snapshot.get('snapshot_run_id')}` / snapshot_date: `{snapshot.get('snapshot_date')}`",
                f"- holding_count: `{snapshot.get('holding_count')}`",
                f"- cash_balance: `{self._fmt_money(snapshot.get('cash_balance'))}` / cash_ratio: `{self._fmt_percent(self._safe_ratio(snapshot.get('cash_balance'), snapshot.get('total_equity')), 2)}`",
                f"- market_value: `{self._fmt_money(snapshot.get('market_value'))}`",
                f"- total_equity: `{self._fmt_money(snapshot.get('total_equity'))}`",
                f"- daily_pnl: `{self._fmt_money(snapshot.get('daily_pnl'))}` / daily_return: `{self._fmt_percent(snapshot.get('daily_return'), 4)}`",
                f"- turnover_amount: `{self._fmt_money(snapshot.get('turnover_amount'))}` / turnover_rate: `{self._fmt_percent(snapshot.get('turnover_rate'), 2)}`",
                "",
                "#### Daily runtime action",
                "",
            ])
            runtime = campaign.get("runtime_observation") or {}
            lines.extend([
                f"- runtime_action: `{runtime.get('runtime_action')}` / campaign_data_status: `{runtime.get('campaign_data_status')}`",
                f"- latest_campaign_date: `{self._json_default(runtime.get('latest_campaign_date'))}` / daily_artifact_exists: `{runtime.get('daily_artifact_exists')}`",
                f"- target_run_id: `{runtime.get('target_run_id')}` / order_run_id: `{runtime.get('order_run_id')}` / fill_run_id: `{runtime.get('fill_run_id')}` / snapshot_run_id: `{runtime.get('snapshot_run_id')}` / position_run_id: `{runtime.get('position_run_id')}`",
                f"- note: {runtime.get('note')}",
                "",
            ])
            trade_explain = self._trade_explanation_counts(
                selection=selection,
                orders=orders or {},
                fills=fills or {},
                snapshot=snapshot,
                risk=campaign.get("risk_metrics") or {},
            )
            reason_samples = self._dedupe_strings(
                item.get("trade_reason_summary") or item.get("trade_reason")
                for item in (campaign.get("trade_details") or [])[:10]
            )
            lines.extend([
                "#### 买卖点与交易说明",
                "",
                f"- target_run_id: `{selection.get('target_run_id')}` / order_run_id: `{(orders or {}).get('order_run_id')}` / fill_run_id: `{(fills or {}).get('fill_run_id')}`",
                f"- buy_count: `{trade_explain.get('buy_count')}` / sell_count: `{trade_explain.get('sell_count')}` / hold_count: `{trade_explain.get('hold_count')}` / skip_count: `{trade_explain.get('skip_count')}`",
                f"- entry_policy: `{trade_explain.get('entry_policy')}` / exit_policy: `{trade_explain.get('exit_policy')}`",
                f"- trade_reason_sample: `{self._dedupe_join(reason_samples[:5], separator=' | ') or 'not_available'}`",
                "",
                "| action | count | policy | reason |",
                "|---|---:|---|---|",
                f"| BUY | {trade_explain.get('buy_count')} | {trade_explain.get('entry_policy')} | 买入来自策略入选、等权目标仓位、价格/成交规则执行。 |",
                f"| SELL | {trade_explain.get('sell_count')} | {trade_explain.get('exit_policy')} | {'当日存在卖出订单，查看交易明细。' if (trade_explain.get('sell_count') or 0) else '当日无卖出订单。'} |",
                f"| HOLD | {trade_explain.get('hold_count')} | position_status=OPEN | 当前持仓仍处于 OPEN 状态，继续纳入生产观察。 |",
                f"| SKIP | {trade_explain.get('skip_count')} | target_without_order_or_rejected | {'存在目标未形成订单或异常订单，需检查原因。' if (trade_explain.get('skip_count') or 0) else '当日目标均已进入订单/成交链路。'} |",
                "",
            ])
            lines.extend(self._render_strategy_trade_decision_explanation(campaign, trade_explain))
            lines.extend(self._render_trade_lifecycle_observation(campaign.get("trade_lifecycle") or {}))
            lines.extend([
                "#### 交易增强摘要",
                "",
                f"- order_total_quantity: `{self._fmt_quantity((orders or {}).get('total_order_quantity'))}` / estimated_gross_amount: `{self._fmt_money((orders or {}).get('total_estimated_gross_amount'))}` / estimated_fee: `{self._fmt_money((orders or {}).get('total_estimated_fee'))}`",
                f"- fill_total_quantity: `{self._fmt_quantity((fills or {}).get('total_fill_quantity'))}` / gross_amount: `{self._fmt_money((fills or {}).get('gross_amount'))}` / total_fee: `{self._fmt_money((fills or {}).get('total_fee_amount'))}` / cash_delta: `{self._fmt_money((fills or {}).get('cash_delta'))}`",
                "",
                "#### 仓位风险摘要",
                "",
            ])
            risk = campaign.get("risk_metrics") or {}
            lines.extend([
                f"- position_rows: `{risk.get('position_rows')}` / open_position_rows: `{risk.get('open_position_rows')}`",
                f"- stock_exposure: `{self._fmt_percent(risk.get('stock_exposure'), 2)}` / max_position_weight: `{self._fmt_percent(risk.get('max_position_weight'), 2)}`",
                f"- total_position_pnl: `{self._fmt_money(risk.get('total_position_pnl'))}` / max_position_pnl: `{self._fmt_money(risk.get('max_position_pnl'))}` / min_position_pnl: `{self._fmt_money(risk.get('min_position_pnl'))}`",
                f"- profitable_position_rows: `{risk.get('profitable_position_rows')}` / losing_position_rows: `{risk.get('losing_position_rows')}`",
                "",
                "#### Campaign 风险检查",
                "",
                "| check | status | reason |",
                "|---|---|---|",
            ])
            for check in campaign.get("campaign_risk_checks") or []:
                lines.append(f"| {check.get('check_name')} | {check.get('status')} | {check.get('reason')} |")
            lines.extend([
                "",
                "#### 入选股票预览",
                "",
                "| rank | code | name | weight | score | source_rank | reason |",
                "|---:|---|---|---:|---:|---:|---|",
            ])
            for item in (campaign.get("selected_instruments") or [])[:30]:
                code = item.get("instrument_code") or item.get("symbol") or item.get("instrument_id")
                lines.append(
                    f"| {item.get('rank_no')} | {code} | {item.get('display_name')} | {self._fmt_percent(item.get('target_weight'), 2)} | {self._fmt_decimal(item.get('score'), 4)} | {item.get('source_rank')} | {item.get('target_reason_code') or item.get('signal_reason_code')} |"
                )
            lines.extend([
                "",
                "#### 交易明细预览",
                "",
                "| side | code | name | target_weight | order_qty | fill_qty | fill_price | entry_policy | exit_policy | gross_amount | fee | order_status | fill_status | trade_reason |",
                "|---|---|---|---:|---:|---:|---:|---|---|---:|---:|---|---|---|",
            ])
            for item in (campaign.get("trade_details") or [])[:30]:
                code = item.get("instrument_code") or item.get("symbol") or item.get("instrument_id")
                lines.append(
                    f"| {item.get('order_side')} | {code} | {item.get('display_name')} | {self._fmt_percent(item.get('target_weight'), 2)} | {self._fmt_quantity(item.get('order_quantity'))} | {self._fmt_quantity(item.get('fill_quantity'))} | {self._fmt_money(item.get('fill_price'))} | {item.get('entry_policy') or ''} | {item.get('exit_policy') or ''} | {self._fmt_money(item.get('gross_amount'))} | {self._fmt_money(item.get('total_fee_amount'))} | {item.get('order_status')} | {item.get('fill_status')} | {item.get('trade_reason_summary') or item.get('trade_reason')} |"
                )
            lines.extend([
                "",
                "#### 交易流水摘要",
                "",
                "| event_type | reason_code | rows | quantity_delta | cash_delta | amount_delta |",
                "|---|---|---:|---:|---:|---:|",
            ])
            for item in campaign.get("ledger_summary") or []:
                lines.append(
                    f"| {item.get('event_type')} | {item.get('reason_code')} | {item.get('rows')} | {self._fmt_quantity(item.get('total_quantity_delta'))} | {self._fmt_money(item.get('total_cash_delta'))} | {self._fmt_money(item.get('total_amount_delta'))} |"
                )
            lines.extend(["", "#### 持仓预览", "", "| code | name | quantity | weight | avg_cost | market_price | market_value | total_pnl | status |", "|---|---|---:|---:|---:|---:|---:|---:|---|"])
            for item in (campaign.get("positions_preview") or [])[:30]:
                code = item.get("instrument_code") or item.get("symbol") or item.get("instrument_id")
                lines.append(
                    f"| {code} | {item.get('display_name')} | {self._fmt_quantity(item.get('quantity'))} | {self._fmt_percent(item.get('position_weight'), 2)} | {self._fmt_money(item.get('avg_cost'))} | {self._fmt_money(item.get('market_price'))} | {self._fmt_money(item.get('market_value'))} | {self._fmt_money(item.get('total_pnl'))} | {item.get('position_status')} |"
                )
            lines.extend(["", "#### 盈亏 Top 观察", "", "| type | code | name | market_value | total_pnl |", "|---|---|---|---:|---:|"])
            for label, rows in (("top_gain", campaign.get("top_gainers") or []), ("top_loss", campaign.get("top_losers") or [])):
                for item in rows[:5]:
                    code = item.get("instrument_code") or item.get("symbol") or item.get("instrument_id")
                    lines.append(f"| {label} | {code} | {item.get('display_name')} | {self._fmt_money(item.get('market_value'))} | {self._fmt_money(item.get('total_pnl'))} |")

            attribution = return_attribution_by_campaign.get(str(campaign.get("campaign_code") or "")) or {}
            benchmark = attribution.get("benchmark_context") or {}
            lines.extend([
                "",
                "#### 收益归因骨架",
                "",
                f"- status: `{attribution.get('status')}` / reason: `{attribution.get('reason')}`",
                f"- scope: `{attribution.get('scope')}`",
                f"- portfolio_daily_return: `{self._fmt_percent(benchmark.get('portfolio_daily_return'), 4)}` / portfolio_daily_pnl: `{self._fmt_money(benchmark.get('portfolio_daily_pnl'))}`",
                f"- market_avg_return: `{self._fmt_percent(benchmark.get('market_avg_return'), 2)}` / selected_avg_return: `{self._fmt_percent(benchmark.get('selected_avg_return'), 2)}` / holding_avg_return: `{self._fmt_percent(benchmark.get('holding_avg_return'), 2)}`",
                f"- portfolio_vs_market: `{self._fmt_percent(benchmark.get('portfolio_vs_market'), 2)}` / selected_vs_market: `{self._fmt_percent(benchmark.get('selected_vs_market'), 2)}` / holding_vs_market: `{self._fmt_percent(benchmark.get('holding_vs_market'), 2)}`",
                f"- top_mainline_tag: `{benchmark.get('top_mainline_tag')}` / top_mainline_match: `{benchmark.get('top_mainline_match')}`",
                "",
                "##### 个股贡献 Top / Bottom",
                "",
                "| type | code | name | weight | market_value | total_pnl | pnl_share | status |",
                "|---|---|---|---:|---:|---:|---:|---|",
            ])
            for label, rows in (("top", attribution.get("individual_top_contributors") or []), ("bottom", attribution.get("individual_bottom_contributors") or [])):
                for item in rows[:5]:
                    code = item.get("instrument_code") or item.get("symbol") or item.get("instrument_id")
                    lines.append(
                        f"| {label} | {code} | {item.get('display_name')} | {self._fmt_percent(item.get('position_weight'), 2)} | {self._fmt_money(item.get('market_value'))} | {self._fmt_money(item.get('total_pnl'))} | {self._fmt_percent(item.get('pnl_share'), 2)} | {item.get('position_status')} |"
                    )
            lines.extend([
                "",
                "##### 行业贡献 Top / Bottom",
                "",
                "| type | industry | holding_count | holding_weight | holding_pnl | market_avg_return | match_status |",
                "|---|---|---:|---:|---:|---:|---|",
            ])
            industry_contribution = attribution.get("industry_contribution") or {}
            for label, rows in (("top", industry_contribution.get("top") or []), ("bottom", industry_contribution.get("bottom") or [])):
                for item in rows[:5]:
                    lines.append(
                        f"| {label} | {item.get('tag_name')} | {item.get('holding_count')} | {self._fmt_percent(item.get('holding_weight'), 2)} | {self._fmt_money(item.get('holding_total_pnl'))} | {self._fmt_percent(item.get('market_avg_pct_change'), 2)} | {item.get('match_status')} |"
                    )
            lines.extend([
                "",
                "##### 概念贡献 Top / Bottom（过滤通用标签）",
                "",
                "| type | concept | holding_count | holding_weight | holding_pnl | market_avg_return | match_status |",
                "|---|---|---:|---:|---:|---:|---|",
            ])
            concept_contribution = attribution.get("concept_contribution") or {}
            for label, rows in (("top", concept_contribution.get("top") or []), ("bottom", concept_contribution.get("bottom") or [])):
                for item in rows[:5]:
                    lines.append(
                        f"| {label} | {item.get('tag_name')} | {item.get('holding_count')} | {self._fmt_percent(item.get('holding_weight'), 2)} | {self._fmt_money(item.get('holding_total_pnl'))} | {self._fmt_percent(item.get('market_avg_pct_change'), 2)} | {item.get('match_status')} |"
                    )
            observation_rows = attribution.get("observation") or []
            if observation_rows:
                lines.extend(["", "##### 归因观察", ""])
                for note in observation_rows[:8]:
                    lines.append(f"- {note}")
            lines.append("")
        lines.extend(["## 4. 风险 / 异常检查", "", "| check | status | reason |", "|---|---|---|"])
        for check in payload.get("checks") or []:
            lines.append(f"| {check.get('check_name')} | {check.get('status')} | {check.get('reason')} |")
        lines.extend(["", "## 5. 产物索引", "", "| campaign | type | path | exists |", "|---|---|---|---|"])
        for row in payload.get("artifact_index") or []:
            lines.append(f"| {row.get('campaign_code')} | {row.get('artifact_type')} | `{row.get('path')}` | {row.get('exists')} |")
        lines.extend(["", "## 6. 观察提示", ""])
        for note in payload.get("observation_notes") or []:
            lines.append(f"- {note}")
        lines.extend(self._render_manual_review_checklist(payload.get("manual_review_checklist") or []))
        lines.append("")
        return "\n".join(lines)

    def _source_rows(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        rows.append({"section": "metadata", "source": "campaign_config", "value": payload.get("campaign_config_path")})
        for item in payload.get("waterline") or []:
            rows.append({"section": "waterline", "source": item.get("table_name"), "value": item.get("max_date"), "status": item.get("status")})
        market_context = payload.get("market_context") or {}
        rows.append({"section": "market_context", "source": "market_breadth", "value": (market_context.get("breadth") or {}).get("market_breadth_state"), "status": market_context.get("status")})
        rows.append({"section": "market_context", "source": "industry_strength", "value": (market_context.get("industry_strength") or {}).get("reason"), "status": (market_context.get("industry_strength") or {}).get("status")})
        rows.append({"section": "market_context", "source": "concept_strength", "value": (market_context.get("concept_strength") or {}).get("reason"), "status": (market_context.get("concept_strength") or {}).get("status")})
        next_trade_plan = payload.get("next_trade_plan") or {}
        rows.append({"section": "next_trade_plan", "source": "meta_trading_calendar", "value": next_trade_plan.get("next_trade_date"), "status": next_trade_plan.get("status")})
        for plan in next_trade_plan.get("campaigns") or []:
            rows.append({"section": "next_trade_plan", "source": plan.get("campaign_code"), "value": plan.get("plan_basis"), "status": plan.get("status")})
        for campaign in payload.get("campaigns") or []:
            rows.append({"section": "campaign", "source": campaign.get("campaign_code"), "value": campaign.get("portfolio_id"), "status": campaign.get("status")})
        return rows


    def _rollback_session_safely(self) -> None:
        """Rollback failed read transaction so later observation queries can continue."""
        try:
            self.session.rollback()
        except Exception:
            pass

    def _rows(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        result = self.session.execute(text(sql), params).mappings().all()
        return [dict(row) for row in result]

    def _one_or_none(self, sql: str, params: dict[str, Any]) -> dict[str, Any] | None:
        result = self.session.execute(text(sql), params).mappings().first()
        return dict(result) if result is not None else None

    def _safe_scalar(self, sql: str, params: dict[str, Any] | None = None) -> Any:
        try:
            return self.session.execute(text(sql), params or {}).scalar()
        except Exception:
            self._rollback_session_safely()
            return None

    def _write_csv(self, path: Path, rows: list[dict[str, Any]]) -> None:
        if not rows:
            path.write_text("", encoding="utf-8-sig")
            return
        fields: list[str] = []
        seen: set[str] = set()
        for row in rows:
            for key in row.keys():
                if key not in seen:
                    fields.append(key)
                    seen.add(key)
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({key: self._csv_cell(row.get(key)) for key in fields})

    @classmethod
    def _fmt_decimal(cls, value: Any, places: int = 2) -> str:
        decimal_value = cls._to_decimal_value(value)
        if decimal_value is None:
            return ""
        quant = Decimal("1") if places <= 0 else Decimal("1").scaleb(-places)
        return f"{decimal_value.quantize(quant):,}"

    @classmethod
    def _fmt_money(cls, value: Any) -> str:
        return cls._fmt_decimal(value, 2)

    @classmethod
    def _fmt_quantity(cls, value: Any) -> str:
        return cls._fmt_decimal(value, 0)

    @classmethod
    def _fmt_percent(cls, value: Any, places: int = 2) -> str:
        decimal_value = cls._to_decimal_value(value)
        if decimal_value is None:
            return ""
        quant = Decimal("1").scaleb(-places)
        return f"{(decimal_value * Decimal('100')).quantize(quant)}%"

    @staticmethod
    def _md_cell(value: Any) -> str:
        if value is None:
            return ""
        text_value = str(value).replace("\r", " ").replace("\n", " ").replace("|", "/")
        return text_value[:500]

    @classmethod
    def _csv_cell(cls, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, default=cls._json_default)
        return str(cls._json_default(value))

    @staticmethod
    def _to_decimal_value(value: Any) -> Decimal | None:
        if value is None or value == "":
            return None
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except Exception:
            return None

    @classmethod
    def _safe_ratio(cls, numerator: Any, denominator: Any) -> Decimal | None:
        num = cls._to_decimal_value(numerator)
        den = cls._to_decimal_value(denominator)
        if num is None or den is None or den == 0:
            return None
        return num / den

    @staticmethod
    def _json_default(value: Any) -> Any:
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        return value

    @staticmethod
    def _to_date(value: Any) -> date | None:
        if value is None:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        return None

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None or value == "":
            return None
        return int(value)

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from stock_quant_v2.api.deps import get_db
from stock_quant_v2.ops_domain.services.m8_daily_ops_service import M8DailyOpsService
from stock_quant_v2.ops_domain.services.m8_human_review_service import M8HumanReviewService
from stock_quant_v2.ops_domain.services.m8_ops_hygiene_service import M8OpsHygieneService
from stock_quant_v2.ops_domain.services.m8_query_service import M8QueryService
from stock_quant_v2.ops_domain.services.m8_report_export_service import M8ReportExportService
from stock_quant_v2.ops_domain.services.m8_scheduler_service import M8SchedulerService

from stock_quant_v2.ops_domain.services.m8_excel_export_service import M8ExcelExportService

from stock_quant_v2.ops_domain.services.m8_alert_log_audit_service import M8AlertLogAuditService

from stock_quant_v2.ops_domain.services.m8_env_startup_service import M8EnvStartupService

router = APIRouter(
    prefix="/api/v1/m8",
    tags=["M8 Ops"],
)


class DailyOpsExportRequest(BaseModel):
    portfolio_id: int = Field(default=1)
    profile_code: str | None = Field(default=None)
    output_dir: str = Field(default="artifacts/m8/daily_ops")


class HumanReviewExportRequest(BaseModel):
    portfolio_id: int = Field(default=1)
    profile_code: str | None = Field(default=None)
    output_dir: str = Field(default="artifacts/m8/human_review")


class OpsSummaryExportRequest(BaseModel):
    portfolio_id: int = Field(default=1)
    profile_code: str | None = Field(default=None)
    output_dir: str = Field(default="artifacts/m8/human_review")


class SchedulerTemplateRequest(BaseModel):
    portfolio_id: int = Field(default=1)
    profile_code: str | None = Field(default=None)
    output_dir: str = Field(default="artifacts/m8/scheduler")
    report_output_dir: str = Field(default="artifacts/m8/daily_ops")
    project_root: str = Field(default=".")
    task_name: str = Field(default="stock_quant_v2_m8_daily_ops")
    schedule_time: str = Field(default="18:30")

class ExcelExportRequest(BaseModel):
    portfolio_id: int = Field(default=1)
    profile_code: str | None = Field(default=None)
    output_dir: str = Field(default="artifacts/m8/excel")

class AlertReportExportRequest(BaseModel):
    portfolio_id: int = Field(default=1)
    profile_code: str | None = Field(default=None)
    output_dir: str = Field(default="artifacts/m8/alert")


class AuditSnapshotExportRequest(BaseModel):
    portfolio_id: int = Field(default=1)
    profile_code: str | None = Field(default=None)
    output_dir: str = Field(default="artifacts/m8/audit")

class EnvReportExportRequest(BaseModel):
    portfolio_id: int = Field(default=1)
    profile_code: str | None = Field(default=None)
    output_dir: str = Field(default="artifacts/m8/env")
    project_root: str = Field(default=".")


def _response(payload: dict[str, Any], *, fail_status_code: int = 500) -> JSONResponse:
    status = payload.get("overall_status")
    status_code = 200

    if status == "FAIL":
        status_code = fail_status_code

    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(
            payload,
            custom_encoder={
                Decimal: str,
                date: lambda v: v.isoformat(),
                datetime: lambda v: v.isoformat(),
                Path: str,
            },
        ),
    )


@router.get("/runs/{run_id}")
def query_run(
    run_id: int,
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = M8QueryService(db).query_run(run_id=run_id)
    if result["overall_status"] == "FAIL":
        raise HTTPException(status_code=404, detail=f"run_id not found: {run_id}")
    return _response(result)


@router.get("/latest-runs")
def query_latest_runs(
    portfolio_id: int = Query(default=1),
    profile_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = M8QueryService(db).query_latest_runs(
        portfolio_id=portfolio_id,
        profile_code=profile_code,
    )
    return _response(result)


@router.get("/paper-chain")
def query_paper_chain(
    portfolio_id: int = Query(default=1),
    target_run_id: int = Query(...),
    order_run_id: int | None = Query(default=None),
    fill_run_id: int | None = Query(default=None),
    position_run_id: int | None = Query(default=None),
    snapshot_run_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = M8QueryService(db).query_paper_chain(
        portfolio_id=portfolio_id,
        target_run_id=target_run_id,
        order_run_id=order_run_id,
        fill_run_id=fill_run_id,
        position_run_id=position_run_id,
        snapshot_run_id=snapshot_run_id,
    )
    return _response(result)


@router.get("/portfolio-snapshot")
def query_portfolio_snapshot(
    portfolio_id: int = Query(default=1),
    snapshot_run_id: int | None = Query(default=None),
    snapshot_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = M8QueryService(db).query_portfolio_snapshot(
        portfolio_id=portfolio_id,
        snapshot_run_id=snapshot_run_id,
        snapshot_date=snapshot_date,
    )
    return _response(result, fail_status_code=404)


@router.get("/risk-profile")
def query_risk_profile(
    profile_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = M8QueryService(db).query_risk_profile(
        profile_code=profile_code,
    )
    return _response(result, fail_status_code=404)


@router.get("/risk-decision")
def query_risk_decision(
    portfolio_id: int = Query(default=1),
    source_target_run_id: int | None = Query(default=None),
    adjusted_target_run_id: int | None = Query(default=None),
    risk_run_id: int | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = M8QueryService(db).query_risk_decision(
        portfolio_id=portfolio_id,
        source_target_run_id=source_target_run_id,
        adjusted_target_run_id=adjusted_target_run_id,
        risk_run_id=risk_run_id,
        limit=limit,
    )
    return _response(result, fail_status_code=404)


@router.get("/target-diff")
def query_target_diff(
    portfolio_id: int = Query(default=1),
    source_target_run_id: int = Query(...),
    adjusted_target_run_id: int = Query(...),
    risk_run_id: int | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = M8QueryService(db).query_target_diff(
        portfolio_id=portfolio_id,
        source_target_run_id=source_target_run_id,
        adjusted_target_run_id=adjusted_target_run_id,
        risk_run_id=risk_run_id,
        limit=limit,
    )
    return _response(result)


@router.get("/daily-ops/check")
def daily_ops_check(
    portfolio_id: int = Query(default=1),
    profile_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = M8DailyOpsService(db).daily_ops_check(
        portfolio_id=portfolio_id,
        profile_code=profile_code,
        export_report=False,
    )
    return _response(result)


@router.get("/daily-ops/plan")
def daily_ops_plan(
    portfolio_id: int = Query(default=1),
    profile_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = M8DailyOpsService(db).daily_ops_plan(
        portfolio_id=portfolio_id,
        profile_code=profile_code,
    )
    return _response(result)


@router.get("/ops-status")
def ops_status_summary(
    portfolio_id: int = Query(default=1),
    profile_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = M8DailyOpsService(db).ops_status_summary(
        portfolio_id=portfolio_id,
        profile_code=profile_code,
    )
    return _response(result)


@router.get("/hygiene-check")
def hygiene_check(
    portfolio_id: int = Query(default=1),
    profile_code: str | None = Query(default=None),
    stale_after_hours: int = Query(default=12, ge=1),
    limit: int = Query(default=200, ge=1, le=5000),
    include_protected: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = M8OpsHygieneService(db).ops_run_hygiene_check(
        portfolio_id=portfolio_id,
        profile_code=profile_code,
        stale_after_hours=stale_after_hours,
        limit=limit,
        include_protected=include_protected,
    )
    return _response(result)


@router.get("/scheduler-health")
def scheduler_health_check(
    portfolio_id: int = Query(default=1),
    profile_code: str | None = Query(default=None),
    output_dir: str = Query(default="artifacts/m8/daily_ops"),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = M8SchedulerService(db).scheduler_health_check(
        portfolio_id=portfolio_id,
        profile_code=profile_code,
        output_dir=Path(output_dir),
    )
    return _response(result)


@router.get("/ops-kpi")
def query_ops_kpi(
    portfolio_id: int = Query(default=1),
    profile_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = M8HumanReviewService(db).query_ops_kpi(
        portfolio_id=portfolio_id,
        profile_code=profile_code,
    )
    return _response(result)


@router.post("/export/daily-ops-report")
def export_daily_ops_report(
    request: DailyOpsExportRequest,
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = M8ReportExportService(db).export_daily_ops_report(
        output_dir=Path(request.output_dir),
        portfolio_id=request.portfolio_id,
        profile_code=request.profile_code,
    )
    return _response(result)


@router.post("/export/human-review-pack")
def export_human_review_pack(
    request: HumanReviewExportRequest,
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = M8HumanReviewService(db).export_human_review_pack(
        output_dir=Path(request.output_dir),
        portfolio_id=request.portfolio_id,
        profile_code=request.profile_code,
    )
    return _response(result)


@router.post("/export/ops-summary-pack")
def export_ops_summary_pack(
    request: OpsSummaryExportRequest,
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = M8HumanReviewService(db).export_ops_summary_pack(
        output_dir=Path(request.output_dir),
        portfolio_id=request.portfolio_id,
        profile_code=request.profile_code,
    )
    return _response(result)


@router.post("/scheduler/windows-task-template")
def generate_windows_task_template(
    request: SchedulerTemplateRequest,
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = M8SchedulerService(db).generate_windows_task_template(
        output_dir=Path(request.output_dir),
        project_root=Path(request.project_root),
        portfolio_id=request.portfolio_id,
        profile_code=request.profile_code,
        report_output_dir=Path(request.report_output_dir),
        task_name=request.task_name,
        schedule_time=request.schedule_time,
    )
    return _response(result)

@router.post("/export/excel/human-review-pack")
def export_excel_human_review_pack(
    request: ExcelExportRequest,
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = M8ExcelExportService(db).export_excel_human_review_pack(
        output_dir=Path(request.output_dir),
        portfolio_id=request.portfolio_id,
        profile_code=request.profile_code,
    )
    return _response(result)


@router.post("/export/excel/daily-ops")
def export_excel_daily_ops(
    request: ExcelExportRequest,
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = M8ExcelExportService(db).export_excel_daily_ops(
        output_dir=Path(request.output_dir),
        portfolio_id=request.portfolio_id,
        profile_code=request.profile_code,
    )
    return _response(result)


@router.post("/export/excel/ops-summary")
def export_excel_ops_summary(
    request: ExcelExportRequest,
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = M8ExcelExportService(db).export_excel_ops_summary(
        output_dir=Path(request.output_dir),
        portfolio_id=request.portfolio_id,
        profile_code=request.profile_code,
    )
    return _response(result)

@router.get("/alert-check")
def ops_alert_check(
    portfolio_id: int = Query(default=1),
    profile_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = M8AlertLogAuditService(db).ops_alert_check(
        portfolio_id=portfolio_id,
        profile_code=profile_code,
    )
    return _response(result)


@router.get("/ops-logs")
def query_ops_logs(
    status: str | None = Query(default=None),
    run_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    include_error_only: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = M8AlertLogAuditService(db).query_ops_logs(
        status=status,
        run_type=run_type,
        limit=limit,
        include_error_only=include_error_only,
    )
    return _response(result)


@router.post("/export/alert-report")
def export_alert_report(
    request: AlertReportExportRequest,
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = M8AlertLogAuditService(db).export_alert_report(
        output_dir=Path(request.output_dir),
        portfolio_id=request.portfolio_id,
        profile_code=request.profile_code,
    )
    return _response(result)


@router.post("/export/audit-snapshot")
def export_audit_snapshot(
    request: AuditSnapshotExportRequest,
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = M8AlertLogAuditService(db).export_audit_snapshot(
        output_dir=Path(request.output_dir),
        portfolio_id=request.portfolio_id,
        profile_code=request.profile_code,
    )
    return _response(result)

@router.get("/env-check")
def env_check(
    portfolio_id: int = Query(default=1),
    profile_code: str | None = Query(default=None),
    project_root: str = Query(default="."),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = M8EnvStartupService(db).env_check(
        portfolio_id=portfolio_id,
        profile_code=profile_code,
        project_root=Path(project_root),
    )
    return _response(result)


@router.get("/startup-check")
def startup_check(
    portfolio_id: int = Query(default=1),
    profile_code: str | None = Query(default=None),
    project_root: str = Query(default="."),
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = M8EnvStartupService(db).startup_check(
        portfolio_id=portfolio_id,
        profile_code=profile_code,
        project_root=Path(project_root),
    )
    return _response(result)


@router.post("/export/env-report")
def export_env_report(
    request: EnvReportExportRequest,
    db: Session = Depends(get_db),
) -> JSONResponse:
    result = M8EnvStartupService(db).export_env_report(
        output_dir=Path(request.output_dir),
        portfolio_id=request.portfolio_id,
        profile_code=request.profile_code,
        project_root=Path(request.project_root),
    )
    return _response(result)
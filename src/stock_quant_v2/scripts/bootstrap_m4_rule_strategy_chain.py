from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import inspect, text

from stock_quant_v2.db.models.meta.instrument import MetaInstrument  # noqa: F401
from stock_quant_v2.db.models.ops.run import OpsRun
from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.strategy_domain.constants import (
    DEFAULT_PARAMETER_VALUES_ALPHA_SELECTION,
    FEATURE_SET_CODE,
    FEATURE_SET_VERSION,
    STRATEGY_CODE_ALPHA_SELECTION,
    STRATEGY_VERSION_CODE_V1,
)
from stock_quant_v2.strategy_domain.tasks import (
    build_alpha_selection_signal,
    seed_alpha_selection_strategy,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _load_runtime_params() -> dict[str, Any]:
    tradable_flag_pass_values_raw = os.getenv("M4_TRADABLE_FLAG_PASS_VALUES", "").strip()

    default_tradable_flag_pass_values = DEFAULT_PARAMETER_VALUES_ALPHA_SELECTION.get(
        "tradable_flag_pass_values"
    )
    if default_tradable_flag_pass_values is None:
        default_tradable_flag_pass_values = [0]

    tradable_flag_pass_values = list(default_tradable_flag_pass_values)
    if tradable_flag_pass_values_raw:
        tradable_flag_pass_values = [
            int(x.strip())
            for x in tradable_flag_pass_values_raw.split(",")
            if x.strip()
        ]

    return {
        "top_n": int(os.getenv("M4_TOP_N", str(DEFAULT_PARAMETER_VALUES_ALPHA_SELECTION["top_n"]))),
        "min_score": float(os.getenv("M4_MIN_SCORE", str(DEFAULT_PARAMETER_VALUES_ALPHA_SELECTION["min_score"]))),
        "require_tradable_flag": _env_bool(
            "M4_REQUIRE_TRADABLE_FLAG",
            DEFAULT_PARAMETER_VALUES_ALPHA_SELECTION["require_tradable_flag"],
        ),
        "tradable_flag_pass_values": tradable_flag_pass_values,
        "weights": {
            "mom": float(os.getenv("M4_WEIGHT_MOM", str(DEFAULT_PARAMETER_VALUES_ALPHA_SELECTION["weights"]["mom"]))),
            "trend": float(
                os.getenv("M4_WEIGHT_TREND", str(DEFAULT_PARAMETER_VALUES_ALPHA_SELECTION["weights"]["trend"]))
            ),
            "low_vol": float(
                os.getenv("M4_WEIGHT_LOW_VOL", str(DEFAULT_PARAMETER_VALUES_ALPHA_SELECTION["weights"]["low_vol"]))
            ),
            "tradability": float(
                os.getenv(
                    "M4_WEIGHT_TRADABILITY",
                    str(DEFAULT_PARAMETER_VALUES_ALPHA_SELECTION["weights"]["tradability"]),
                )
            ),
        },
    }


def _resolve_signal_as_of_date(session) -> tuple[date | None, date]:
    """
    M4 as_of_date 解析规则：
    1. 如果显式提供 M4_SIGNAL_AS_OF_DATE，则把它当作“上限日期”；
    2. 否则不设上限；
    3. 从 analytics_feature_snapshot 中取 <= 上限日期 的最新 ready 日期；
    4. 返回 (requested_as_of_date, resolved_as_of_date)。
    """
    env_value = os.getenv("M4_SIGNAL_AS_OF_DATE", "").strip()
    requested_as_of_date = date.fromisoformat(env_value) if env_value else None

    sql = """
        SELECT trade_date
        FROM analytics_feature_snapshot
        WHERE feature_set_code = :feature_set_code
          AND feature_set_version = :feature_set_version
          AND sample_status = 'ready'
          AND feature_code IN (
              'feat_mom_20',
              'feat_trend_strength_20',
              'feat_volatility_rank_20',
              'feat_tradability_score',
              'feat_tradable_flag'
          )
    """

    params: dict[str, Any] = {
        "feature_set_code": FEATURE_SET_CODE,
        "feature_set_version": FEATURE_SET_VERSION,
    }

    if requested_as_of_date is not None:
        sql += " AND trade_date <= :requested_as_of_date"
        params["requested_as_of_date"] = requested_as_of_date

    sql += """
        GROUP BY trade_date
        HAVING COUNT(DISTINCT feature_code) = 5
        ORDER BY trade_date DESC
        LIMIT 1
    """

    resolved_as_of_date = session.execute(text(sql), params).scalar_one_or_none()

    if resolved_as_of_date is None:
        if requested_as_of_date is not None:
            raise RuntimeError(
                f"未找到 <= {requested_as_of_date} 的可用 analytics_feature_snapshot ready 日期。"
                "请先确认 M3 feature 已生成。"
            )
        raise RuntimeError(
            "未找到可用于 M4 的 analytics_feature_snapshot ready 日期。"
            "请先确认 M3 feature 已生成。"
        )

    return requested_as_of_date, resolved_as_of_date


def _resolve_next_trade_date(session, as_of_date: date) -> date:
    """
    优先从 meta_trading_calendar 取下一交易日。
    """
    inspector = inspect(session.bind)
    table_name = "meta_trading_calendar"

    if not inspector.has_table(table_name):
        raise RuntimeError("未找到 meta_trading_calendar 表，无法计算 effective_date。")

    columns = {col["name"] for col in inspector.get_columns(table_name)}

    date_col_candidates = ["trade_date", "calendar_date", "trading_date"]
    open_flag_candidates = ["is_open", "is_trading_day", "is_trade_day"]

    date_col = next((x for x in date_col_candidates if x in columns), None)
    if date_col is None:
        raise RuntimeError(
            f"meta_trading_calendar 缺少交易日日期列，当前列为: {sorted(columns)}"
        )

    open_flag_col = next((x for x in open_flag_candidates if x in columns), None)

    sql = f"SELECT MIN({date_col}) AS next_trade_date FROM {table_name} WHERE {date_col} > :as_of_date"
    params = {"as_of_date": as_of_date}

    if open_flag_col is not None:
        sql += f" AND {open_flag_col} = true"

    next_trade_date = session.execute(text(sql), params).scalar_one_or_none()
    if next_trade_date is None:
        raise RuntimeError(f"未找到 {as_of_date} 之后的下一交易日。")

    return next_trade_date


def _create_run(
    session,
    *,
    requested_as_of_date: date | None,
    resolved_as_of_date: date,
    runtime_params: dict[str, Any],
) -> OpsRun:
    run = OpsRun(
        run_uid=uuid.uuid4(),
        run_type="strategy_signal_build",
        run_name="bootstrap_m4_rule_strategy_chain",
        status="RUNNING",
        trigger_type="manual",
        requested_at=_utcnow(),
        started_at=_utcnow(),
        context_json={
            "requested_as_of_date": requested_as_of_date.isoformat() if requested_as_of_date else None,
            "resolved_as_of_date": resolved_as_of_date.isoformat(),
            "strategy_code": STRATEGY_CODE_ALPHA_SELECTION,
            "strategy_version_code": STRATEGY_VERSION_CODE_V1,
            "feature_set_code": FEATURE_SET_CODE,
            "feature_set_version": FEATURE_SET_VERSION,
            "parameters": runtime_params,
        },
        error_message=None,
    )
    session.add(run)
    session.flush()
    return run


def main() -> None:
    runtime_params = _load_runtime_params()

    with SessionLocal() as session:
        requested_as_of_date, as_of_date = _resolve_signal_as_of_date(session)

        try:
            strategy_version_id = seed_alpha_selection_strategy(session)
            run = _create_run(
                session,
                requested_as_of_date=requested_as_of_date,
                resolved_as_of_date=as_of_date,
                runtime_params=runtime_params,
            )
            effective_date = _resolve_next_trade_date(session, as_of_date=as_of_date)

            build_result = build_alpha_selection_signal(
                session,
                run_id=run.id,
                strategy_version_id=strategy_version_id,
                as_of_date=as_of_date,
                effective_date=effective_date,
                runtime_params=runtime_params,
            )

            run.status = "SUCCESS"
            run.ended_at = _utcnow()
            run.error_message = None

            result = {
                "run_id": run.id,
                "strategy_code": STRATEGY_CODE_ALPHA_SELECTION,
                "strategy_version_code": STRATEGY_VERSION_CODE_V1,
                "feature_set_code": FEATURE_SET_CODE,
                "feature_set_version": FEATURE_SET_VERSION,
                "requested_as_of_date": requested_as_of_date.isoformat() if requested_as_of_date else None,
                "resolved_as_of_date": as_of_date.isoformat(),
                "fallback_used": (
                    requested_as_of_date is not None and requested_as_of_date != as_of_date
                ),
                "effective_date": effective_date.isoformat(),
                **build_result,
                "top_n": runtime_params["top_n"],
                "min_score": runtime_params["min_score"],
            }

            session.commit()
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

        except Exception as exc:
            session.rollback()
            print(
                json.dumps(
                    {
                        "status": "FAILED",
                        "strategy_code": STRATEGY_CODE_ALPHA_SELECTION,
                        "requested_as_of_date": requested_as_of_date.isoformat() if requested_as_of_date else None,
                        "resolved_as_of_date": as_of_date.isoformat(),
                        "error": str(exc),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            raise


if __name__ == "__main__":
    main()
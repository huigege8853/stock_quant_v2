from __future__ import annotations

from sqlalchemy.orm import Session

from stock_quant_v2.analytics_domain.constants import LABEL_CODES
from stock_quant_v2.analytics_domain.repositories.analytics_definition_repository import AnalyticsDefinitionRepository


SEED_LABELS: list[dict] = [
    {
        "label_code": LABEL_CODES["LABEL_FWD_RET_5D"],
        "label_name": "Forward Return 5D",
        "label_type": "regression",
        "horizon_days": 5,
        "target_expr": "adj_close[t+5] / adj_close[t] - 1",
        "price_basis": "adj_close",
        "barrier_rule_json": {},
        "publish_lag_days": 1,
        "leakage_guard_rule_json": {"strict_future_only": True},
        "version": "v1",
        "is_active": True,
        "description": "5个未来交易日收益率",
    },
    {
        "label_code": LABEL_CODES["LABEL_FWD_RET_10D"],
        "label_name": "Forward Return 10D",
        "label_type": "regression",
        "horizon_days": 10,
        "target_expr": "adj_close[t+10] / adj_close[t] - 1",
        "price_basis": "adj_close",
        "barrier_rule_json": {},
        "publish_lag_days": 1,
        "leakage_guard_rule_json": {"strict_future_only": True},
        "version": "v1",
        "is_active": True,
        "description": "10个未来交易日收益率",
    },
    {
        "label_code": LABEL_CODES["LABEL_UP_5D_GE_3PCT"],
        "label_name": "Up 5D >= 3%",
        "label_type": "classification",
        "horizon_days": 5,
        "target_expr": "fwd_ret_5d >= 0.03",
        "price_basis": "adj_close",
        "barrier_rule_json": {"threshold": 0.03},
        "publish_lag_days": 1,
        "leakage_guard_rule_json": {"strict_future_only": True},
        "version": "v1",
        "is_active": True,
        "description": "未来5个交易日收益率大于等于3%",
    },
    {
        "label_code": LABEL_CODES["LABEL_DOWN_5D_LE_M3PCT"],
        "label_name": "Down 5D <= -3%",
        "label_type": "classification",
        "horizon_days": 5,
        "target_expr": "fwd_ret_5d <= -0.03",
        "price_basis": "adj_close",
        "barrier_rule_json": {"threshold": -0.03},
        "publish_lag_days": 1,
        "leakage_guard_rule_json": {"strict_future_only": True},
        "version": "v1",
        "is_active": True,
        "description": "未来5个交易日收益率小于等于-3%",
    },
]


def run(session: Session) -> int:
    repo = AnalyticsDefinitionRepository(session=session)
    count = 0
    for item in SEED_LABELS:
        repo.upsert_label_definition(item)
        count += 1
    session.commit()
    return count
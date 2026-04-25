from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


DEFAULT_PROFILE_CODE = "paper_cn_a_default_risk_v1"

DEFAULT_RULES: list[dict[str, Any]] = [
    {
        "rule_code": "R001_MAX_POSITION_COUNT",
        "rule_name": "最大持仓数",
        "rule_type": "POSITION_LIMIT",
        "default_action": "REJECT",
        "default_params_json": {"max_position_count": 30},
        "priority": 10,
    },
    {
        "rule_code": "R002_MAX_SINGLE_POSITION_WEIGHT",
        "rule_name": "单票最大权重",
        "rule_type": "POSITION_LIMIT",
        "default_action": "ADJUST",
        "default_params_json": {"max_weight": "0.05", "lot_size": "100"},
        "priority": 20,
    },
    {
        "rule_code": "R003_SUSPENDED_FILTER",
        "rule_name": "停牌过滤",
        "rule_type": "TRADABILITY",
        "default_action": "REJECT",
        "default_params_json": {"missing_status_action": "WARN"},
        "priority": 30,
    },
    {
        "rule_code": "R004_PRICE_LIMIT_FILTER",
        "rule_name": "涨跌停过滤",
        "rule_type": "TRADABILITY",
        "default_action": "ADJUST",
        "default_params_json": {
            "buy_at_up_limit_action": "REJECT",
            "sell_at_down_limit_action": "ADJUST_TO_CURRENT",
            "tolerance": "0.0001",
        },
        "priority": 40,
    },
    {
        "rule_code": "R005_MISSING_PRICE_FILTER",
        "rule_name": "缺价检查",
        "rule_type": "DATA_READINESS",
        "default_action": "WARN",
        "default_params_json": {"missing_effective_price_action": "WARN"},
        "priority": 50,
    },
    {
        "rule_code": "R006_LOT_SIZE_CHECK",
        "rule_name": "A股手数检查",
        "rule_type": "ORDER_CONSTRAINT",
        "default_action": "ADJUST",
        "default_params_json": {"lot_size": "100"},
        "priority": 60,
    },
]


class RiskProfileSeedService:
    def __init__(self, session: Session):
        self.session = session

    def seed_default_profile(
        self,
        *,
        profile_code: str = DEFAULT_PROFILE_CODE,
        profile_name: str = "CN A Paper Trading Default Risk Profile V1",
    ) -> dict[str, Any]:
        rule_ids: dict[str, int] = {}

        for rule in DEFAULT_RULES:
            rule_id = self._upsert_rule(rule)
            rule_ids[rule["rule_code"]] = rule_id

        profile_id = self._upsert_profile(
            profile_code=profile_code,
            profile_name=profile_name,
        )

        for rule in DEFAULT_RULES:
            self._upsert_profile_rule(
                profile_id=profile_id,
                rule_id=rule_ids[rule["rule_code"]],
                priority=int(rule["priority"]),
                action=str(rule["default_action"]),
                params_json=rule["default_params_json"],
            )

        return {
            "profile_id": profile_id,
            "profile_code": profile_code,
            "rule_count": len(DEFAULT_RULES),
            "rules": sorted(rule_ids.keys()),
            "status": "SUCCESS",
        }

    def _upsert_rule(self, rule: dict[str, Any]) -> int:
        row = self.session.execute(
            text("select id from risk_rule where rule_code = :rule_code"),
            {"rule_code": rule["rule_code"]},
        ).mappings().first()

        params = {
            "rule_code": rule["rule_code"],
            "rule_name": rule["rule_name"],
            "rule_type": rule["rule_type"],
            "default_action": rule["default_action"],
            "default_params_json": json.dumps(rule["default_params_json"], ensure_ascii=False),
            "description": rule.get("description"),
        }

        if row is None:
            return int(
                self.session.execute(
                    text(
                        """
                        insert into risk_rule (
                            rule_code, rule_name, rule_type, default_action,
                            default_params_json, enabled, description, created_at, updated_at
                        )
                        values (
                            :rule_code, :rule_name, :rule_type, :default_action,
                            cast(:default_params_json as jsonb), true, :description, now(), now()
                        )
                        returning id
                        """
                    ),
                    params,
                ).scalar_one()
            )

        self.session.execute(
            text(
                """
                update risk_rule
                set rule_name = :rule_name,
                    rule_type = :rule_type,
                    default_action = :default_action,
                    default_params_json = cast(:default_params_json as jsonb),
                    enabled = true,
                    description = :description,
                    updated_at = now()
                where rule_code = :rule_code
                """
            ),
            params,
        )
        return int(row["id"])

    def _upsert_profile(self, *, profile_code: str, profile_name: str) -> int:
        row = self.session.execute(
            text("select id from risk_profile where profile_code = :profile_code"),
            {"profile_code": profile_code},
        ).mappings().first()

        if row is None:
            return int(
                self.session.execute(
                    text(
                        """
                        insert into risk_profile (
                            profile_code, profile_name, profile_type, market_code,
                            enabled, description, created_at, updated_at
                        )
                        values (
                            :profile_code, :profile_name, 'PAPER_TRADING', 'CN_A',
                            true, 'M7-Risk default paper trading profile', now(), now()
                        )
                        returning id
                        """
                    ),
                    {"profile_code": profile_code, "profile_name": profile_name},
                ).scalar_one()
            )

        self.session.execute(
            text(
                """
                update risk_profile
                set profile_name = :profile_name,
                    enabled = true,
                    updated_at = now()
                where profile_code = :profile_code
                """
            ),
            {"profile_code": profile_code, "profile_name": profile_name},
        )
        return int(row["id"])

    def _upsert_profile_rule(
        self,
        *,
        profile_id: int,
        rule_id: int,
        priority: int,
        action: str,
        params_json: dict[str, Any],
    ) -> None:
        exists = self.session.execute(
            text(
                """
                select id
                from risk_profile_rule
                where profile_id = :profile_id
                  and rule_id = :rule_id
                """
            ),
            {"profile_id": profile_id, "rule_id": rule_id},
        ).mappings().first()

        params = {
            "profile_id": profile_id,
            "rule_id": rule_id,
            "priority": priority,
            "action": action,
            "params_json": json.dumps(params_json, ensure_ascii=False),
        }

        if exists is None:
            self.session.execute(
                text(
                    """
                    insert into risk_profile_rule (
                        profile_id, rule_id, priority, action, params_json,
                        enabled, created_at, updated_at
                    )
                    values (
                        :profile_id, :rule_id, :priority, :action,
                        cast(:params_json as jsonb), true, now(), now()
                    )
                    """
                ),
                params,
            )
        else:
            self.session.execute(
                text(
                    """
                    update risk_profile_rule
                    set priority = :priority,
                        action = :action,
                        params_json = cast(:params_json as jsonb),
                        enabled = true,
                        updated_at = now()
                    where profile_id = :profile_id
                      and rule_id = :rule_id
                    """
                ),
                params,
            )

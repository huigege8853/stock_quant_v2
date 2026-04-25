from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


RISK3_RULES: dict[str, dict[str, Any]] = {
    "R007_INDUSTRY_MAX_WEIGHT": {
        "rule_name": "行业最大权重",
        "rule_type": "EXPOSURE",
        "default_action": "ADJUST",
        "default_params_json": {
            "max_industry_weight": "0.25",
            "lot_size": "100",
            "missing_industry_action": "WARN",
        },
        "description": "Cap aggregate target exposure by industry.",
    },
    "R009_MARKET_RISK_SWITCH": {
        "rule_name": "市场风险开关",
        "rule_type": "MARKET_RISK",
        "default_action": "ADJUST",
        "default_params_json": {
            "market_risk_mode": "NORMAL",
            "gross_exposure_multiplier": "1.0",
        },
        "description": "Global market risk control: NORMAL / REDUCE / NO_BUY / LIQUIDATE.",
    },
    "R011_LIQUIDITY_FILTER": {
        "rule_name": "流动性约束",
        "rule_type": "LIQUIDITY",
        "default_action": "ADJUST",
        "default_params_json": {
            "min_turnover_amount": "0",
            "max_participation_rate": "0.10",
            "lot_size": "100",
            "missing_liquidity_action": "WARN",
        },
        "description": "Minimum liquidity and max participation cap using latest daily bar amount/volume.",
    },
}


RISK3_PROFILES: list[dict[str, Any]] = [
    {
        "profile_code": "paper_cn_a_risk3_observe_v1",
        "profile_name": "CN A Risk3 Observe Profile V1",
        "description": "Observation mode: record industry/liquidity/market warnings without changing targets.",
        "rules": {
            "R007_INDUSTRY_MAX_WEIGHT": {
                "priority": 70,
                "action": "WARN",
                "params_json": {
                    "max_industry_weight": "0.30",
                    "lot_size": "100",
                    "missing_industry_action": "WARN",
                },
            },
            "R009_MARKET_RISK_SWITCH": {
                "priority": 90,
                "action": "WARN",
                "params_json": {
                    "market_risk_mode": "NORMAL",
                    "gross_exposure_multiplier": "1.0",
                },
            },
            "R011_LIQUIDITY_FILTER": {
                "priority": 110,
                "action": "WARN",
                "params_json": {
                    "min_turnover_amount": "0",
                    "max_participation_rate": "0.10",
                    "lot_size": "100",
                    "missing_liquidity_action": "WARN",
                },
            },
        },
    },
    {
        "profile_code": "paper_cn_a_risk3_conservative_v1",
        "profile_name": "CN A Risk3 Conservative Profile V1",
        "description": "Conservative mode: cap industry, reduce gross exposure, cap participation.",
        "rules": {
            "R007_INDUSTRY_MAX_WEIGHT": {
                "priority": 70,
                "action": "ADJUST",
                "params_json": {
                    "max_industry_weight": "0.20",
                    "lot_size": "100",
                    "missing_industry_action": "WARN",
                },
            },
            "R009_MARKET_RISK_SWITCH": {
                "priority": 90,
                "action": "ADJUST",
                "params_json": {
                    "market_risk_mode": "REDUCE",
                    "gross_exposure_multiplier": "0.90",
                    "lot_size": "100",
                },
            },
            "R011_LIQUIDITY_FILTER": {
                "priority": 110,
                "action": "ADJUST",
                "params_json": {
                    "min_turnover_amount": "10000000",
                    "max_participation_rate": "0.10",
                    "lot_size": "100",
                    "missing_liquidity_action": "WARN",
                },
            },
        },
    },
    {
        "profile_code": "paper_cn_a_risk3_strict_v1",
        "profile_name": "CN A Risk3 Strict Profile V1",
        "description": "Strict mode: missing industry or liquidity rejects targets, market switch blocks new buys.",
        "rules": {
            "R007_INDUSTRY_MAX_WEIGHT": {
                "priority": 70,
                "action": "REJECT",
                "params_json": {
                    "max_industry_weight": "0.15",
                    "lot_size": "100",
                    "missing_industry_action": "REJECT",
                },
            },
            "R009_MARKET_RISK_SWITCH": {
                "priority": 90,
                "action": "ADJUST",
                "params_json": {
                    "market_risk_mode": "NO_BUY",
                    "gross_exposure_multiplier": "1.0",
                    "lot_size": "100",
                },
            },
            "R011_LIQUIDITY_FILTER": {
                "priority": 110,
                "action": "REJECT",
                "params_json": {
                    "min_turnover_amount": "50000000",
                    "max_participation_rate": "0.05",
                    "lot_size": "100",
                    "missing_liquidity_action": "REJECT",
                },
            },
        },
    },
]


class Risk3ProfileSeedService:
    def __init__(self, session: Session):
        self.session = session

    def seed(self) -> dict[str, Any]:
        rule_ids: dict[str, int] = {}
        for rule_code, rule in RISK3_RULES.items():
            rule_ids[rule_code] = self._upsert_rule(rule_code=rule_code, rule=rule)

        profiles_out = []
        for profile in RISK3_PROFILES:
            profile_id = self._upsert_profile(profile)
            for rule_code, rule_cfg in profile["rules"].items():
                self._upsert_profile_rule(
                    profile_id=profile_id,
                    rule_id=rule_ids[rule_code],
                    priority=int(rule_cfg["priority"]),
                    action=str(rule_cfg["action"]),
                    params_json=dict(rule_cfg["params_json"]),
                )
            profiles_out.append(
                {
                    "profile_id": profile_id,
                    "profile_code": profile["profile_code"],
                    "rule_count": len(profile["rules"]),
                    "status": "SUCCESS",
                }
            )

        return {
            "profiles": profiles_out,
            "rules": sorted(rule_ids.keys()),
            "status": "SUCCESS",
        }

    def _upsert_rule(self, *, rule_code: str, rule: dict[str, Any]) -> int:
        row = self.session.execute(
            text("select id from risk_rule where rule_code = :rule_code"),
            {"rule_code": rule_code},
        ).mappings().first()

        params = {
            "rule_code": rule_code,
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

    def _upsert_profile(self, profile: dict[str, Any]) -> int:
        row = self.session.execute(
            text("select id from risk_profile where profile_code = :profile_code"),
            {"profile_code": profile["profile_code"]},
        ).mappings().first()

        params = {
            "profile_code": profile["profile_code"],
            "profile_name": profile["profile_name"],
            "description": profile["description"],
        }

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
                            true, :description, now(), now()
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
                update risk_profile
                set profile_name = :profile_name,
                    description = :description,
                    enabled = true,
                    updated_at = now()
                where profile_code = :profile_code
                """
            ),
            params,
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
        row = self.session.execute(
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

        if row is None:
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
            return

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

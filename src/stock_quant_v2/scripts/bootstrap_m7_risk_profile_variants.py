from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from stock_quant_v2.db.session import SessionLocal


PROFILES: list[dict[str, Any]] = [
    {
        "profile_code": "paper_cn_a_default_risk_v1",
        "profile_name": "CN A Paper Trading Default Risk Profile V1",
        "description": "Default profile. Missing data is WARN. Max single weight is 5%.",
        "rules": {
            "R001_MAX_POSITION_COUNT": {"action": "REJECT", "params": {"max_position_count": 30}, "priority": 10},
            "R002_MAX_SINGLE_POSITION_WEIGHT": {"action": "ADJUST", "params": {"max_weight": "0.05", "lot_size": "100"}, "priority": 20},
            "R003_SUSPENDED_FILTER": {"action": "REJECT", "params": {"missing_status_action": "WARN"}, "priority": 30},
            "R004_PRICE_LIMIT_FILTER": {
                "action": "ADJUST",
                "params": {
                    "buy_at_up_limit_action": "REJECT",
                    "sell_at_down_limit_action": "ADJUST_TO_CURRENT",
                    "tolerance": "0.0001",
                },
                "priority": 40,
            },
            "R005_MISSING_PRICE_FILTER": {"action": "WARN", "params": {"missing_effective_price_action": "WARN"}, "priority": 50},
            "R006_LOT_SIZE_CHECK": {"action": "ADJUST", "params": {"lot_size": "100"}, "priority": 60},
        },
    },
    {
        "profile_code": "paper_cn_a_conservative_risk_v1",
        "profile_name": "CN A Paper Trading Conservative Risk Profile V1",
        "description": "Conservative profile. Max single weight is 3%, causing target down-adjustment.",
        "rules": {
            "R001_MAX_POSITION_COUNT": {"action": "REJECT", "params": {"max_position_count": 30}, "priority": 10},
            "R002_MAX_SINGLE_POSITION_WEIGHT": {"action": "ADJUST", "params": {"max_weight": "0.03", "lot_size": "100"}, "priority": 20},
            "R003_SUSPENDED_FILTER": {"action": "REJECT", "params": {"missing_status_action": "WARN"}, "priority": 30},
            "R004_PRICE_LIMIT_FILTER": {
                "action": "ADJUST",
                "params": {
                    "buy_at_up_limit_action": "REJECT",
                    "sell_at_down_limit_action": "ADJUST_TO_CURRENT",
                    "tolerance": "0.0001",
                },
                "priority": 40,
            },
            "R005_MISSING_PRICE_FILTER": {"action": "WARN", "params": {"missing_effective_price_action": "WARN"}, "priority": 50},
            "R006_LOT_SIZE_CHECK": {"action": "ADJUST", "params": {"lot_size": "100"}, "priority": 60},
        },
    },
    {
        "profile_code": "paper_cn_a_data_strict_risk_v1",
        "profile_name": "CN A Paper Trading Data Strict Risk Profile V1",
        "description": "Strict data readiness profile. Missing effective-date price rejects targets.",
        "rules": {
            "R001_MAX_POSITION_COUNT": {"action": "REJECT", "params": {"max_position_count": 30}, "priority": 10},
            "R002_MAX_SINGLE_POSITION_WEIGHT": {"action": "ADJUST", "params": {"max_weight": "0.05", "lot_size": "100"}, "priority": 20},
            "R003_SUSPENDED_FILTER": {"action": "REJECT", "params": {"missing_status_action": "WARN"}, "priority": 30},
            "R004_PRICE_LIMIT_FILTER": {
                "action": "ADJUST",
                "params": {
                    "buy_at_up_limit_action": "REJECT",
                    "sell_at_down_limit_action": "ADJUST_TO_CURRENT",
                    "tolerance": "0.0001",
                },
                "priority": 40,
            },
            "R005_MISSING_PRICE_FILTER": {"action": "REJECT", "params": {"missing_effective_price_action": "REJECT"}, "priority": 50},
            "R006_LOT_SIZE_CHECK": {"action": "ADJUST", "params": {"lot_size": "100"}, "priority": 60},
        },
    },
]


RULE_META: dict[str, dict[str, str]] = {
    "R001_MAX_POSITION_COUNT": {
        "rule_name": "最大持仓数",
        "rule_type": "POSITION_LIMIT",
        "default_action": "REJECT",
    },
    "R002_MAX_SINGLE_POSITION_WEIGHT": {
        "rule_name": "单票最大权重",
        "rule_type": "POSITION_LIMIT",
        "default_action": "ADJUST",
    },
    "R003_SUSPENDED_FILTER": {
        "rule_name": "停牌过滤",
        "rule_type": "TRADABILITY",
        "default_action": "REJECT",
    },
    "R004_PRICE_LIMIT_FILTER": {
        "rule_name": "涨跌停过滤",
        "rule_type": "TRADABILITY",
        "default_action": "ADJUST",
    },
    "R005_MISSING_PRICE_FILTER": {
        "rule_name": "缺价检查",
        "rule_type": "DATA_READINESS",
        "default_action": "WARN",
    },
    "R006_LOT_SIZE_CHECK": {
        "rule_name": "A股手数检查",
        "rule_type": "ORDER_CONSTRAINT",
        "default_action": "ADJUST",
    },
}


def _upsert_rule(session, rule_code: str, profile_rule: dict[str, Any]) -> int:
    meta = RULE_META[rule_code]
    row = session.execute(
        text("select id from risk_rule where rule_code = :rule_code"),
        {"rule_code": rule_code},
    ).mappings().first()

    params = {
        "rule_code": rule_code,
        "rule_name": meta["rule_name"],
        "rule_type": meta["rule_type"],
        "default_action": meta["default_action"],
        "default_params_json": json.dumps(profile_rule["params"], ensure_ascii=False),
    }

    if row is None:
        return int(
            session.execute(
                text(
                    """
                    insert into risk_rule (
                        rule_code, rule_name, rule_type, default_action,
                        default_params_json, enabled, created_at, updated_at
                    )
                    values (
                        :rule_code, :rule_name, :rule_type, :default_action,
                        cast(:default_params_json as jsonb), true, now(), now()
                    )
                    returning id
                    """
                ),
                params,
            ).scalar_one()
        )

    session.execute(
        text(
            """
            update risk_rule
            set rule_name = :rule_name,
                rule_type = :rule_type,
                default_action = :default_action,
                default_params_json = cast(:default_params_json as jsonb),
                enabled = true,
                updated_at = now()
            where rule_code = :rule_code
            """
        ),
        params,
    )
    return int(row["id"])


def _upsert_profile(session, profile: dict[str, Any]) -> int:
    row = session.execute(
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
            session.execute(
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

    session.execute(
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


def _upsert_profile_rule(session, *, profile_id: int, rule_id: int, rule_config: dict[str, Any]) -> None:
    row = session.execute(
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
        "priority": int(rule_config["priority"]),
        "action": rule_config["action"],
        "params_json": json.dumps(rule_config["params"], ensure_ascii=False),
    }

    if row is None:
        session.execute(
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

    session.execute(
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


def main() -> None:
    session = SessionLocal()
    try:
        output = []
        for profile in PROFILES:
            profile_id = _upsert_profile(session, profile)
            for rule_code, rule_config in profile["rules"].items():
                rule_id = _upsert_rule(session, rule_code, rule_config)
                _upsert_profile_rule(
                    session,
                    profile_id=profile_id,
                    rule_id=rule_id,
                    rule_config=rule_config,
                )
            output.append(
                {
                    "profile_id": profile_id,
                    "profile_code": profile["profile_code"],
                    "rule_count": len(profile["rules"]),
                    "status": "SUCCESS",
                }
            )

        session.commit()
        print(json.dumps({"profiles": output, "status": "SUCCESS"}, ensure_ascii=False, indent=2))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()

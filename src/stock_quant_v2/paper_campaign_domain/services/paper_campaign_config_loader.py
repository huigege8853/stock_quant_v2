from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from stock_quant_v2.paper_campaign_domain.dto.paper_campaign_models import PaperCampaignConfig


class PaperCampaignConfigLoader:
    """Load M6.5 paper campaign configs from a local JSON file.

    Accepted JSON shapes:
    - [ {...}, {...} ]
    - { "campaigns": [ {...}, {...} ] }

    The loader is deliberately strict about portfolio_id=1.  P1 should not
    accidentally reuse the production main paper portfolio unless the operator
    explicitly sets allow_main_portfolio=true.
    """

    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path

    def exists(self) -> bool:
        return self.config_path.exists()

    def load(self) -> list[PaperCampaignConfig]:
        if not self.config_path.exists():
            return []

        raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            items = raw.get("campaigns", [])
        else:
            items = raw

        if not isinstance(items, list):
            raise ValueError("paper campaign config must be a list or {'campaigns': [...]} object")

        # DISABLED campaigns are kept in active_campaigns.json for history and
        # traceability, but they must not be parsed into runnable M6.5 configs.
        # This intentionally happens before _parse_item(), because legacy
        # disabled campaigns may use archival-only values such as
        # run_mode=manual that are not valid for the automatic daily runner.
        return [self._parse_item(item) for item in items if not self._is_disabled_item(item)]

    @staticmethod
    def _is_disabled_item(item: Any) -> bool:
        if not isinstance(item, dict):
            return False
        return str(item.get("status") or "ACTIVE").strip().upper() == "DISABLED"

    @staticmethod
    def _parse_item(item: dict[str, Any]) -> PaperCampaignConfig:
        if not isinstance(item, dict):
            raise ValueError(f"campaign item must be an object: {item!r}")

        campaign_code = str(item.get("campaign_code") or "").strip()
        if not campaign_code:
            raise ValueError("campaign_code is required")

        strategy_code = str(item.get("strategy_code") or "").strip()
        if not strategy_code:
            raise ValueError(f"strategy_code is required for campaign {campaign_code}")

        portfolio_id = _optional_int(item.get("portfolio_id"))
        allow_main = _bool(item.get("allow_main_portfolio"), False)
        if portfolio_id == 1 and not allow_main:
            raise ValueError(
                f"campaign {campaign_code} uses portfolio_id=1. "
                "This is blocked by default to avoid polluting the production main portfolio. "
                "Set allow_main_portfolio=true only for an explicit one-off test."
            )

        planned_days = int(item.get("planned_trading_days") or 20)
        if planned_days <= 0:
            raise ValueError(f"planned_trading_days must be positive for campaign {campaign_code}")

        target_count = int(item.get("target_count") or 30)
        if target_count <= 0:
            raise ValueError(f"target_count must be positive for campaign {campaign_code}")

        run_mode = str(item.get("run_mode") or "auto").strip().lower()
        if run_mode not in {"auto", "m6", "m7", "skip"}:
            raise ValueError(f"invalid run_mode for campaign {campaign_code}: {run_mode}")

        status = str(item.get("status") or "ACTIVE").strip().upper()
        if status not in {"ACTIVE", "PAUSED", "COMPLETED", "FAILED"}:
            raise ValueError(f"invalid status for campaign {campaign_code}: {status}")

        known = {
            "campaign_code",
            "campaign_name",
            "strategy_code",
            "strategy_version_code",
            "account_code",
            "portfolio_code",
            "account_id",
            "portfolio_id",
            "initial_cash",
            "planned_trading_days",
            "start_trade_date",
            "status",
            "run_mode",
            "target_count",
            "replace_existing",
            "allow_main_portfolio",
            "run_m9_finalizers",
        }

        return PaperCampaignConfig(
            campaign_code=campaign_code,
            campaign_name=str(item.get("campaign_name") or campaign_code),
            strategy_code=strategy_code,
            strategy_version_code=str(item.get("strategy_version_code") or "v1"),
            account_code=_optional_str(item.get("account_code")),
            portfolio_code=_optional_str(item.get("portfolio_code")),
            account_id=_optional_int(item.get("account_id")),
            portfolio_id=portfolio_id,
            initial_cash=Decimal(str(item.get("initial_cash") or "10000000")),
            planned_trading_days=planned_days,
            start_trade_date=_optional_date(item.get("start_trade_date")),
            status=status,  # type: ignore[arg-type]
            run_mode=run_mode,  # type: ignore[arg-type]
            target_count=target_count,
            replace_existing=_bool(item.get("replace_existing"), False),
            allow_main_portfolio=allow_main,
            run_m9_finalizers=_bool(item.get("run_m9_finalizers"), False),
            extra={k: v for k, v in item.items() if k not in known},
        )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _optional_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _bool(value: Any, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

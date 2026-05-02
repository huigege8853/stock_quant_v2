from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from stock_quant_v2.paper_campaign_domain.services.paper_campaign_runner import PaperCampaignRunner


def run_paper_campaign_daily(
    *,
    project_root: Path,
    config_path: Path,
    trade_date: date | None = None,
    campaign_code: str | None = None,
    dry_run: bool = False,
    python_executable: str | None = None,
) -> dict[str, Any]:
    runner = PaperCampaignRunner(
        project_root=project_root,
        python_executable=python_executable or "python",
    )
    return runner.run_daily(
        config_path=config_path,
        trade_date=trade_date,
        campaign_code=campaign_code,
        dry_run=dry_run,
    )

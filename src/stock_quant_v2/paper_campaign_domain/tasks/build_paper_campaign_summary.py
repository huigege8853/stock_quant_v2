from __future__ import annotations

from pathlib import Path
from typing import Any

from stock_quant_v2.paper_campaign_domain.services.paper_campaign_runner import PaperCampaignRunner


def build_paper_campaign_summary(
    *,
    project_root: Path,
    config_path: Path,
    campaign_code: str,
    python_executable: str | None = None,
) -> dict[str, Any]:
    runner = PaperCampaignRunner(
        project_root=project_root,
        python_executable=python_executable or "python",
    )
    return runner.build_summary(config_path=config_path, campaign_code=campaign_code)

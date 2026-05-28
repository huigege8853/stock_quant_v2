"""CLI preview entrypoint for R64 research adapter skeleton.

This script is a research-only preview shell. It does not read or write production
signals, does not write DB, and does not trade.
"""

from __future__ import annotations

import argparse
import json

from stock_quant_v2.strategy_domain.services.multi_layer_regime_rotation_v2_research_adapter import (
    MultiLayerRegimeRotationV2ResearchAdapter,
    R64AdapterConfig,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema-name", default="research_ops")
    parser.add_argument("--strategy-code", default="multi_layer_regime_rotation_v2")
    parser.add_argument("--strategy-version-code", default="v1_l0_l12_state_budget_theme_style")
    parser.add_argument("--full-decision-version", default="r64_l0_l12_state_skeleton_v3")
    parser.add_argument("--plan-version", default="r64_prototype_candidate_plan_v1")
    parser.add_argument("--backtest-version", default="r64_research_prototype_backtest_dryrun_v1")
    parser.add_argument("--top-n", type=int, default=50)
    args = parser.parse_args()

    adapter = MultiLayerRegimeRotationV2ResearchAdapter(
        R64AdapterConfig(
            schema_name=args.schema_name,
            strategy_code=args.strategy_code,
            strategy_version_code=args.strategy_version_code,
            full_decision_version=args.full_decision_version,
            plan_version=args.plan_version,
            backtest_version=args.backtest_version,
            top_n=args.top_n,
        )
    )
    payload = adapter.build_signal_preview()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

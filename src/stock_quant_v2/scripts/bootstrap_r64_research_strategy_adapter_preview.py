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
    R64_SHADOW_ARTIFACT_VERSION,
    R64_STRATEGY_COMPARE_INPUT_DRYRUN_ARTIFACT_VERSION,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema-name", default="research_ops")
    parser.add_argument("--strategy-code", default="multi_layer_regime_rotation_v2")
    parser.add_argument("--strategy-version-code", default="v1_l0_l12_state_budget_theme_style")
    parser.add_argument("--full-decision-version", default="r64_l0_l12_state_skeleton_v3")
    parser.add_argument("--plan-version", default="r64_prototype_candidate_plan_v1")
    parser.add_argument("--backtest-version", default="r64_research_prototype_backtest_dryrun_v1")
    parser.add_argument("--shadow-artifact-version", default=R64_SHADOW_ARTIFACT_VERSION)
    parser.add_argument("--top-n", type=int, default=50)
    parser.add_argument(
        "--sample-shadow-candidate",
        action="store_true",
        help="Emit a deterministic in-memory shadow candidate artifact; no DB writes are performed.",
    )
    parser.add_argument(
        "--emit-backtest-request-dryrun-candidate",
        action="store_true",
        help="Emit only the M5-compatible R64 backtest request dry-run candidate artifact.",
    )
    parser.add_argument(
        "--emit-strategy-compare-input-dryrun-candidate",
        action="store_true",
        help="Emit only the R64 strategy compare input dry-run candidate artifact.",
    )
    parser.add_argument(
        "--emit-report-generation-dryrun-candidate",
        action="store_true",
        help="Emit only the R64 report generation dry-run candidate artifact.",
    )
    args = parser.parse_args()

    adapter = MultiLayerRegimeRotationV2ResearchAdapter(
        R64AdapterConfig(
            schema_name=args.schema_name,
            strategy_code=args.strategy_code,
            strategy_version_code=args.strategy_version_code,
            full_decision_version=args.full_decision_version,
            plan_version=args.plan_version,
            backtest_version=args.backtest_version,
            shadow_artifact_version=args.shadow_artifact_version,
            top_n=args.top_n,
        )
    )
    if args.emit_report_generation_dryrun_candidate:
        payload = adapter.build_report_generation_dryrun_candidate(shadow_signal_row_count=0)
    elif args.emit_strategy_compare_input_dryrun_candidate:
        payload = adapter.build_strategy_compare_input_dryrun_candidate(shadow_signal_row_count=0)
    elif args.emit_backtest_request_dryrun_candidate:
        payload = adapter.build_backtest_request_dryrun_candidate(shadow_signal_row_count=0)
    elif args.sample_shadow_candidate:
        payload = adapter.build_candidate_preview(
            decision_rows=[{"layer": "L7", "status": "preview"}],
            candidate_rows=[{"ts_code": "000001.SZ", "score": 0.0}],
        )
    else:
        payload = adapter.build_signal_preview()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

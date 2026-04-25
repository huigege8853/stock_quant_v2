#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/app}"
export TZ="${TZ:-Asia/Shanghai}"

cd "$PROJECT_ROOT"

python -m stock_quant_v2.scripts.bootstrap_daily_project_runtime_chain "$@"

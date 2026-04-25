#!/usr/bin/env bash
set -euo pipefail

cd /app

mkdir -p /app/logs
mkdir -p /app/artifacts
mkdir -p /app/strategy_release_cache

echo "[daily] started at $(date '+%F %T %Z')"

python /app/scripts/sync_strategy_release.py
python -m stock_quant_v2.scripts.bootstrap_daily_project_runtime_chain

echo "[daily] finished at $(date '+%F %T %Z')"
from __future__ import annotations

"""Compatibility module for run result writing services.

The current M5.10 patch writes backtest metrics through the existing
RunResultRepository.replace_backtest_metrics interface and writes artifacts / series
inside BacktestRealExecutionService. This module is intentionally kept import-safe
because the uploaded baseline file was empty and no stable public API has been
locked for it yet.
"""

__all__: list[str] = []

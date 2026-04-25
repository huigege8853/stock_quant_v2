from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass
class BackfillFetchResult:
    exchange_code: str
    ticker: str
    provider_name: str | None
    success: bool
    rows: list[dict]
    error: str | None


def run_concurrent_symbol_fetch(
    *,
    items: Sequence[dict],
    worker_fn: Callable[[dict], BackfillFetchResult],
    max_workers: int = 12,
) -> tuple[list[BackfillFetchResult], dict[str, int], dict[str, int], dict[str, int]]:
    if not items:
        return [], {}, {}, {}

    results: list[BackfillFetchResult] = []
    provider_success_counter: dict[str, int] = defaultdict(int)
    provider_empty_counter: dict[str, int] = defaultdict(int)
    provider_error_counter: dict[str, int] = defaultdict(int)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(worker_fn, item) for item in items]

        for future in as_completed(futures):
            result = future.result()
            results.append(result)

            if result.success and result.rows:
                if result.provider_name:
                    provider_success_counter[result.provider_name] += len(result.rows)
            else:
                if result.provider_name:
                    if result.error:
                        provider_error_counter[result.provider_name] += 1
                    else:
                        provider_empty_counter[result.provider_name] += 1

    return (
        results,
        dict(provider_success_counter),
        dict(provider_empty_counter),
        dict(provider_error_counter),
    )
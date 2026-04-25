"""MarketIndexBar second-chain tasks template.

This file is a first-pass implementation template based on the current handoff:
- Reuse DailyBar first-chain patterns (run registration -> raw -> staging -> core -> quality/lineage -> versioning)
- Keep scope small for first E2E validation: a few core indexes and 2-5 trading days
- Provider fallback should start simple and observable before expanding throughput

Assumptions to verify in repository before merge:
1. run_repository / sync_run_repository interfaces are aligned with DailyBar tasks implementation.
2. raw/staging/core repository methods already exist or can be added with similar signatures.
3. provider_fallback_service can dispatch a market_index_bar dataset key.
4. market_index lookup repository can resolve market_index_id from code / provider symbol.
5. DTO / mapper for MarketIndexBar either already exists or will be added alongside this tasks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Iterable, Sequence


@dataclass(slots=True)
class MarketIndexBarSyncRequest:
    market_codes: Sequence[str] | None = None
    start_date: date | None = None
    end_date: date | None = None
    price_adjust_type: str = "none"
    debug_mode: bool = True
    debug_limit_symbols: int | None = 10
    batch_size: int = 50
    force_repair: bool = False
    run_reason: str = "bootstrap_market_index_first_chain"


@dataclass(slots=True)
class ProviderFetchResult:
    provider: str
    market_code: str
    trade_date: date
    payload: dict[str, Any] | None
    is_empty: bool = False
    error_message: str | None = None


@dataclass(slots=True)
class MarketIndexBarSyncStats:
    input_rows: int = 0
    raw_rows: int = 0
    staging_rows: int = 0
    core_upsert_rows: int = 0
    error_rows: int = 0
    skipped_batches: int = 0
    provider_success_counter: dict[str, int] = field(default_factory=dict)
    provider_empty_counter: dict[str, int] = field(default_factory=dict)
    provider_error_counter: dict[str, int] = field(default_factory=dict)

    def bump(self, bucket: dict[str, int], provider: str, delta: int = 1) -> None:
        bucket[provider] = bucket.get(provider, 0) + delta


class MarketIndexBarSyncTask:
    """First-pass tasks shell for the MarketIndexBar second chain.

    Recommended rollout:
    - Phase 1: 4 core indexes, 2-5 trade dates, manual verification
    - Phase 2: widen date range, add repair path, improve provider telemetry
    - Phase 3: add data-version publish gate and reconciliation sampling
    """

    DATASET_CODE = "market_index_bar"
    FALLBACK_CHAIN = ("tushare", "sina", "akshare", "skip")

    def __init__(
        self,
        session_factory: Any,
        run_repository: Any,
        sync_run_repository: Any,
        raw_repository: Any,
        staging_repository: Any,
        core_repository: Any,
        data_version_repository: Any,
        provider_fallback_service: Any,
        quality_service: Any,
        lineage_service: Any,
        market_index_lookup_repository: Any,
        checkpoint_service: Any | None = None,
        logger: Any | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._run_repository = run_repository
        self._sync_run_repository = sync_run_repository
        self._raw_repository = raw_repository
        self._staging_repository = staging_repository
        self._core_repository = core_repository
        self._data_version_repository = data_version_repository
        self._provider_fallback_service = provider_fallback_service
        self._quality_service = quality_service
        self._lineage_service = lineage_service
        self._market_index_lookup_repository = market_index_lookup_repository
        self._checkpoint_service = checkpoint_service
        self._logger = logger

    def execute(self, request: MarketIndexBarSyncRequest) -> dict[str, Any]:
        stats = MarketIndexBarSyncStats()
        session = self._session_factory()
        run_id = None
        sync_run_id = None
        data_version_id = None
        try:
            run_id = self._open_run(session=session, request=request)
            sync_run_id = self._open_sync_run(session=session, run_id=run_id, request=request)

            sync_plan = self._build_sync_plan(session=session, request=request)
            stats.input_rows = len(sync_plan)

            if not sync_plan:
                return self._close_empty_run(
                    session=session,
                    run_id=run_id,
                    sync_run_id=sync_run_id,
                    request=request,
                    stats=stats,
                )

            for batch in self._iter_batches(sync_plan, request.batch_size):
                batch_results = self._fetch_batch(session=session, batch=batch, request=request, stats=stats)
                raw_rows = self._write_raw(session=session, sync_run_id=sync_run_id, results=batch_results)
                stats.raw_rows += raw_rows

                staging_rows = self._standardize_to_staging(
                    session=session,
                    sync_run_id=sync_run_id,
                    batch_results=batch_results,
                    request=request,
                )
                stats.staging_rows += staging_rows

                core_upsert_rows = self._upsert_core(
                    session=session,
                    sync_run_id=sync_run_id,
                    batch_results=batch_results,
                    request=request,
                )
                stats.core_upsert_rows += core_upsert_rows

                self._record_lineage_and_quality(
                    session=session,
                    sync_run_id=sync_run_id,
                    batch_results=batch_results,
                    request=request,
                )
                session.commit()

            data_version_id = self._publish_data_version_if_eligible(
                session=session,
                request=request,
                stats=stats,
            )
            self._close_success_run(
                session=session,
                run_id=run_id,
                sync_run_id=sync_run_id,
                request=request,
                stats=stats,
                data_version_id=data_version_id,
            )
            session.commit()
            return self._build_result_payload(stats=stats, data_version_id=data_version_id)
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            self._mark_failed_run(session=session, run_id=run_id, sync_run_id=sync_run_id, error=exc)
            session.commit()
            raise
        finally:
            session.close()

    def _build_sync_plan(self, session: Any, request: MarketIndexBarSyncRequest) -> list[dict[str, Any]]:
        market_indexes = self._market_index_lookup_repository.list_active_market_indexes(
            session=session,
            market_codes=request.market_codes,
            limit=request.debug_limit_symbols if request.debug_mode else None,
        )
        trading_dates = self._market_index_lookup_repository.list_trading_dates(
            session=session,
            start_date=request.start_date,
            end_date=request.end_date,
        )
        plan: list[dict[str, Any]] = []
        for market_index in market_indexes:
            for trade_date in trading_dates:
                plan.append(
                    {
                        "market_index_id": market_index.id,
                        "market_code": market_index.code,
                        "provider_symbol": getattr(market_index, "provider_symbol", market_index.code),
                        "trade_date": trade_date,
                    }
                )
        return plan

    def _fetch_batch(
        self,
        session: Any,
        batch: Sequence[dict[str, Any]],
        request: MarketIndexBarSyncRequest,
        stats: MarketIndexBarSyncStats,
    ) -> list[ProviderFetchResult]:
        results: list[ProviderFetchResult] = []
        for item in batch:
            provider_result = self._provider_fallback_service.fetch_with_fallback(
                dataset_code=self.DATASET_CODE,
                providers=self.FALLBACK_CHAIN,
                request={
                    "market_code": item["market_code"],
                    "provider_symbol": item["provider_symbol"],
                    "trade_date": item["trade_date"],
                    "price_adjust_type": request.price_adjust_type,
                },
            )
            normalized = ProviderFetchResult(
                provider=provider_result.provider,
                market_code=item["market_code"],
                trade_date=item["trade_date"],
                payload=provider_result.payload,
                is_empty=getattr(provider_result, "is_empty", False),
                error_message=getattr(provider_result, "error_message", None),
            )
            self._update_provider_stats(stats=stats, result=normalized)
            results.append(normalized)
        return results

    def _update_provider_stats(self, stats: MarketIndexBarSyncStats, result: ProviderFetchResult) -> None:
        if result.error_message:
            stats.error_rows += 1
            stats.bump(stats.provider_error_counter, result.provider)
            return
        if result.is_empty or not result.payload:
            stats.bump(stats.provider_empty_counter, result.provider)
            return
        stats.bump(stats.provider_success_counter, result.provider)

    def _write_raw(self, session: Any, sync_run_id: int, results: Sequence[ProviderFetchResult]) -> int:
        raw_records = []
        for result in results:
            if not result.payload:
                continue
            raw_records.append(
                {
                    "sync_run_id": sync_run_id,
                    "dataset_code": self.DATASET_CODE,
                    "business_key": f"{result.market_code}:{result.trade_date.isoformat()}",
                    "source_provider": result.provider,
                    "payload_json": self._json_safe(result.payload),
                    "trade_date": result.trade_date,
                }
            )
        if not raw_records:
            return 0
        return self._raw_repository.bulk_insert_market_index_bar_raw(session=session, rows=raw_records)

    def _standardize_to_staging(
        self,
        session: Any,
        sync_run_id: int,
        batch_results: Sequence[ProviderFetchResult],
        request: MarketIndexBarSyncRequest,
    ) -> int:
        staging_rows = []
        for result in batch_results:
            if not result.payload:
                continue
            staging_rows.append(
                {
                    "sync_run_id": sync_run_id,
                    "market_code": result.market_code,
                    "trade_date": result.trade_date,
                    "price_adjust_type": request.price_adjust_type,
                    "open": self._to_decimal(result.payload.get("open")),
                    "high": self._to_decimal(result.payload.get("high")),
                    "low": self._to_decimal(result.payload.get("low")),
                    "close": self._to_decimal(result.payload.get("close")),
                    "pre_close": self._to_decimal(result.payload.get("pre_close")),
                    "volume": self._to_decimal(result.payload.get("volume")),
                    "amount": self._to_decimal(result.payload.get("amount")),
                    "source_provider": result.provider,
                }
            )
        if not staging_rows:
            return 0
        return self._staging_repository.bulk_insert_market_index_bar_staging(session=session, rows=staging_rows)

    def _upsert_core(
        self,
        session: Any,
        sync_run_id: int,
        batch_results: Sequence[ProviderFetchResult],
        request: MarketIndexBarSyncRequest,
    ) -> int:
        core_rows = []
        lookup = self._market_index_lookup_repository.get_market_index_id_map(
            session=session,
            market_codes=[r.market_code for r in batch_results],
        )
        for result in batch_results:
            if not result.payload:
                continue
            market_index_id = lookup.get(result.market_code)
            if market_index_id is None:
                continue
            core_rows.append(
                {
                    "market_index_id": market_index_id,
                    "trade_date": result.trade_date,
                    "price_adjust_type": request.price_adjust_type,
                    "open": self._to_decimal(result.payload.get("open")),
                    "high": self._to_decimal(result.payload.get("high")),
                    "low": self._to_decimal(result.payload.get("low")),
                    "close": self._to_decimal(result.payload.get("close")),
                    "pre_close": self._to_decimal(result.payload.get("pre_close")),
                    "volume": self._to_decimal(result.payload.get("volume")),
                    "amount": self._to_decimal(result.payload.get("amount")),
                    "source_provider": result.provider,
                }
            )
        if not core_rows:
            return 0
        return self._core_repository.bulk_upsert_market_index_bar(
            session=session,
            rows=core_rows,
            index_elements=["market_index_id", "trade_date", "price_adjust_type"],
        )

    def _record_lineage_and_quality(
        self,
        session: Any,
        sync_run_id: int,
        batch_results: Sequence[ProviderFetchResult],
        request: MarketIndexBarSyncRequest,
    ) -> None:
        self._lineage_service.record_dataset_lineage(
            session=session,
            sync_run_id=sync_run_id,
            dataset_code=self.DATASET_CODE,
            target_dataset_code="core_market_index_bar",
        )
        self._quality_service.evaluate_market_index_bar_batch(
            session=session,
            sync_run_id=sync_run_id,
            results=batch_results,
            request=request,
        )

    def _publish_data_version_if_eligible(
        self,
        session: Any,
        request: MarketIndexBarSyncRequest,
        stats: MarketIndexBarSyncStats,
    ) -> int | None:
        if stats.core_upsert_rows <= 0:
            return None
        error_rate = (stats.error_rows / stats.input_rows) if stats.input_rows else 0
        if error_rate > 0.05:
            return None
        return self._data_version_repository.create_data_version(
            session=session,
            dataset_code=self.DATASET_CODE,
            version_desc=(
                f"MarketIndexBar second-chain bootstrap: rows={stats.core_upsert_rows}, "
                f"range={request.start_date}~{request.end_date}"
            ),
            publish_status="published",
        )

    def _open_run(self, session: Any, request: MarketIndexBarSyncRequest) -> int:
        return self._run_repository.create_run(
            session=session,
            run_type="data_sync",
            run_reason=request.run_reason,
            run_status="running",
        )

    def _open_sync_run(self, session: Any, run_id: int, request: MarketIndexBarSyncRequest) -> int:
        return self._sync_run_repository.create_sync_run(
            session=session,
            run_id=run_id,
            dataset_code=self.DATASET_CODE,
            sync_status="running",
            request_payload={
                "market_codes": list(request.market_codes or []),
                "start_date": request.start_date.isoformat() if request.start_date else None,
                "end_date": request.end_date.isoformat() if request.end_date else None,
                "price_adjust_type": request.price_adjust_type,
            },
        )

    def _close_empty_run(
        self,
        session: Any,
        run_id: int,
        sync_run_id: int,
        request: MarketIndexBarSyncRequest,
        stats: MarketIndexBarSyncStats,
    ) -> dict[str, Any]:
        self._sync_run_repository.mark_succeeded(
            session=session,
            sync_run_id=sync_run_id,
            result_payload=self._build_result_payload(stats=stats, data_version_id=None),
        )
        self._run_repository.mark_succeeded(session=session, run_id=run_id)
        session.commit()
        return self._build_result_payload(stats=stats, data_version_id=None)

    def _close_success_run(
        self,
        session: Any,
        run_id: int,
        sync_run_id: int,
        request: MarketIndexBarSyncRequest,
        stats: MarketIndexBarSyncStats,
        data_version_id: int | None,
    ) -> None:
        self._sync_run_repository.mark_succeeded(
            session=session,
            sync_run_id=sync_run_id,
            result_payload=self._build_result_payload(stats=stats, data_version_id=data_version_id),
        )
        self._run_repository.mark_succeeded(session=session, run_id=run_id)

    def _mark_failed_run(self, session: Any, run_id: int | None, sync_run_id: int | None, error: Exception) -> None:
        if sync_run_id is not None:
            self._sync_run_repository.mark_failed(
                session=session,
                sync_run_id=sync_run_id,
                error_message=str(error),
            )
        if run_id is not None:
            self._run_repository.mark_failed(session=session, run_id=run_id, error_message=str(error))

    @staticmethod
    def _iter_batches(items: Sequence[dict[str, Any]], batch_size: int) -> Iterable[Sequence[dict[str, Any]]]:
        for start in range(0, len(items), batch_size):
            yield items[start : start + batch_size]

    @staticmethod
    def _to_decimal(value: Any) -> Decimal | None:
        if value is None or value == "":
            return None
        return Decimal(str(value))

    @staticmethod
    def _json_safe(payload: dict[str, Any]) -> dict[str, Any]:
        safe: dict[str, Any] = {}
        for key, value in payload.items():
            if isinstance(value, (date, Decimal)):
                safe[key] = str(value)
            else:
                safe[key] = value
        return safe

    @staticmethod
    def _build_result_payload(stats: MarketIndexBarSyncStats, data_version_id: int | None) -> dict[str, Any]:
        return {
            "input_rows": stats.input_rows,
            "raw_rows": stats.raw_rows,
            "staging_rows": stats.staging_rows,
            "core_upsert_rows": stats.core_upsert_rows,
            "error_rows": stats.error_rows,
            "skipped_batches": stats.skipped_batches,
            "provider_success_counter": stats.provider_success_counter,
            "provider_empty_counter": stats.provider_empty_counter,
            "provider_error_counter": stats.provider_error_counter,
            "data_version_id": data_version_id,
        }

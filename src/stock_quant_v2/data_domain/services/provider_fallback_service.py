from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Generic, TypeVar

T = TypeVar("T")


@dataclass(slots=True)
class ProviderAttemptDetail:
    provider_name: str
    success: bool
    row_count: int = 0
    error: str | None = None
    skipped: bool = False
    skipped_reason: str | None = None


@dataclass(slots=True)
class ProviderAttemptResult(Generic[T]):
    provider_name: str | None
    success: bool
    data: list[T] | None = None
    error: str | None = None
    attempts: list[ProviderAttemptDetail] = field(default_factory=list)


class ProviderFallbackService:
    def try_providers(
        self,
        providers: list[tuple[str, Callable[[], list[T]]]],
        skipped_providers: dict[str, str] | None = None,
    ) -> ProviderAttemptResult[T]:
        attempts: list[ProviderAttemptDetail] = []

        if not providers and not skipped_providers:
            return ProviderAttemptResult(
                provider_name=None,
                success=False,
                data=None,
                error="no providers configured",
                attempts=attempts,
            )

        skipped_provider_map = {
            str(provider_name).lower(): reason
            for provider_name, reason in (skipped_providers or {}).items()
        }

        last_error: str | None = None

        for provider_name, fetch_func in providers:
            normalized_provider_name = str(provider_name).lower()

            if normalized_provider_name in skipped_provider_map:
                attempts.append(
                    ProviderAttemptDetail(
                        provider_name=provider_name,
                        success=False,
                        row_count=0,
                        error=None,
                        skipped=True,
                        skipped_reason=skipped_provider_map[normalized_provider_name],
                    )
                )
                continue

            try:
                rows = fetch_func()
                if rows:
                    attempts.append(
                        ProviderAttemptDetail(
                            provider_name=provider_name,
                            success=True,
                            row_count=len(rows),
                            error=None,
                            skipped=False,
                            skipped_reason=None,
                        )
                    )
                    return ProviderAttemptResult(
                        provider_name=provider_name,
                        success=True,
                        data=rows,
                        error=None,
                        attempts=attempts,
                    )

                attempts.append(
                    ProviderAttemptDetail(
                        provider_name=provider_name,
                        success=False,
                        row_count=0,
                        error="empty rows",
                        skipped=False,
                        skipped_reason=None,
                    )
                )
                last_error = f"{provider_name} returned empty rows"

            except Exception as exc:  # noqa: BLE001
                attempts.append(
                    ProviderAttemptDetail(
                        provider_name=provider_name,
                        success=False,
                        row_count=0,
                        error=str(exc),
                        skipped=False,
                        skipped_reason=None,
                    )
                )
                last_error = f"{provider_name}: {exc}"

        if skipped_provider_map and not attempts:
            return ProviderAttemptResult(
                provider_name=None,
                success=False,
                data=None,
                error="all providers skipped",
                attempts=[],
            )

        return ProviderAttemptResult(
            provider_name=None,
            success=False,
            data=None,
            error=last_error or "all providers failed or were skipped",
            attempts=attempts,
        )
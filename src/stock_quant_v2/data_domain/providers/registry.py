from __future__ import annotations

from collections.abc import Callable
from typing import Any


class ProviderRegistry:
    def __init__(self) -> None:
        self._factories: dict[tuple[str, str], Callable[..., Any]] = {}

    def register(self, provider_name: str, dataset_code: str, factory: Callable[..., Any]) -> None:
        key = (provider_name.lower(), dataset_code.lower())
        self._factories[key] = factory

    def has_provider(self, provider_name: str, dataset_code: str) -> bool:
        key = (provider_name.lower(), dataset_code.lower())
        return key in self._factories

    def build(self, provider_name: str, dataset_code: str, **kwargs: Any) -> Any:
        key = (provider_name.lower(), dataset_code.lower())
        if key not in self._factories:
            raise KeyError(f"Provider not registered: {key}")
        return self._factories[key](**kwargs)
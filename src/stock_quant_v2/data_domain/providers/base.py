from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, Iterable, TypeVar

TRequest = TypeVar("TRequest")
TDTO = TypeVar("TDTO")


class BaseProvider(ABC, Generic[TRequest, TDTO]):
    provider_name: str
    dataset_code: str

    @abstractmethod
    def fetch(self, request: TRequest) -> Iterable[TDTO]:
        raise NotImplementedError
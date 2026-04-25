from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TypeVar

T = TypeVar("T")


def iter_chunks(items: Sequence[T] | list[T], chunk_size: int) -> Iterable[list[T]]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")

    total = len(items)
    for start in range(0, total, chunk_size):
        yield list(items[start:start + chunk_size])
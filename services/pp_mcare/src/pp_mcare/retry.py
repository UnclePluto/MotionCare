from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar


T = TypeVar("T")


def run_with_retry(
    operation: Callable[[], T],
    *,
    attempts: int,
    sleeper: Callable[[float], None],
    retryable: tuple[type[Exception], ...],
    on_retry: Callable[[int, Exception], None],
) -> T:
    """运行一次操作；仅对调用方声明的异常做有限递增退避。"""
    if isinstance(attempts, bool) or attempts < 1:
        raise ValueError("attempts 必须是正整数")
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except retryable as error:
            if attempt == attempts:
                raise
            on_retry(attempt, error)
            sleeper(float(attempt))
    raise AssertionError("unreachable")

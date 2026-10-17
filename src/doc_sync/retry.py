"""Bounded retries for explicitly transient synchronization failures."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from .errors import TransientSyncError

T = TypeVar("T")


def run_with_retries(
    operation: Callable[[], T],
    *,
    max_retries: int = 3,
    backoff_seconds: tuple[float, ...] = (1.0, 2.0, 4.0),
    sleep: Callable[[float], None] = time.sleep,
    on_retry: Callable[[int, TransientSyncError], None] | None = None,
) -> T:
    if max_retries < 0 or max_retries > len(backoff_seconds):
        raise ValueError("max_retries must fit the configured backoff schedule.")
    attempts = 0
    while True:
        try:
            return operation()
        except TransientSyncError as error:
            if attempts >= max_retries:
                raise
            attempts += 1
            if on_retry is not None:
                on_retry(attempts, error)
            sleep(backoff_seconds[attempts - 1])

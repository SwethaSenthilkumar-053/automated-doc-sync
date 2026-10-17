import pytest

from doc_sync.errors import TransientSyncError
from doc_sync.retry import run_with_retries


def test_retries_transient_error_then_succeeds():
    attempts = 0
    delays = []

    def operation():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TransientSyncError("temporary")
        return "ok"

    assert run_with_retries(operation, sleep=delays.append) == "ok"
    assert attempts == 3
    assert delays == [1.0, 2.0]


def test_stops_after_three_retries():
    attempts = 0

    def operation():
        nonlocal attempts
        attempts += 1
        raise TransientSyncError("temporary")

    with pytest.raises(TransientSyncError):
        run_with_retries(operation, sleep=lambda _: None)
    assert attempts == 4


def test_does_not_retry_terminal_error():
    attempts = 0

    def operation():
        nonlocal attempts
        attempts += 1
        raise ValueError("invalid")

    with pytest.raises(ValueError):
        run_with_retries(operation, sleep=lambda _: None)
    assert attempts == 1

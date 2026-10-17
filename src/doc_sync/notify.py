"""Notification boundary; default implementation never claims external delivery."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol


class Notifier(Protocol):
    def notify(self, subject: str, message: str) -> None:
        """Deliver a maintainer notification."""


@dataclass
class LoggingNotifier:
    logger: logging.Logger = logging.getLogger("doc_sync")

    def notify(self, subject: str, message: str) -> None:
        self.logger.error("Notification required: %s: %s", subject, message)


class CallbackNotifier:
    """Adapter for a host-provided notifier, such as a GitHub API integration."""

    def __init__(self, callback: object) -> None:
        if not callable(callback):
            raise TypeError("notification callback must be callable")
        self._callback = callback

    def notify(self, subject: str, message: str) -> None:
        self._callback(subject, message)  # type: ignore[operator]

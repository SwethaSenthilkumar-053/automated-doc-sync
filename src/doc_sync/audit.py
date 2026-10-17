"""Structured audit records for sync attempts."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

Outcome = Literal["success", "no-op", "partial", "failed"]


@dataclass
class AuditRecord:
    triggering_prs: list[int] = field(default_factory=list)
    changed_paths: list[str] = field(default_factory=list)
    generated_paths: list[str] = field(default_factory=list)
    outcome: Outcome = "success"
    started_at: str = field(default_factory=lambda: _timestamp())
    completed_at: str | None = None
    details: list[str] = field(default_factory=list)

    def complete(self, outcome: Outcome) -> None:
        self.outcome = outcome
        self.completed_at = _timestamp()

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(self), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()

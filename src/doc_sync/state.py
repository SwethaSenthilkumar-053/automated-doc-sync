"""Atomic local state storage with replay-safe unresolved target tracking.

This file-backed backend is useful for local runs. A CI deployment must provide
durable storage shared across workflow runs before enabling automatic checkpointing.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from .errors import StateConflictError, SyncError


@dataclass
class SyncState:
    last_success_sha: str | None = None
    unresolved: dict[str, list[str]] = field(default_factory=dict)
    revision: int = 0
    generated_hashes: dict[str, str] = field(default_factory=dict)


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> SyncState:
        if not self.path.exists():
            return SyncState()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if (
                not isinstance(raw, dict)
                or raw.get("version") != 1
                or type(raw.get("revision")) is not int
                or raw["revision"] < 0
                or not isinstance(raw.get("unresolved"), dict)
                or (raw.get("last_success_sha") is not None and not _valid_sha(raw["last_success_sha"]))
                or not isinstance(raw.get("generated_hashes", {}), dict)
            ):
                raise ValueError("unexpected state structure")
            unresolved = raw["unresolved"]
            generated_hashes = raw.get("generated_hashes", {})
            if not all(
                isinstance(key, str)
                and isinstance(value, list)
                and all(isinstance(item, str) for item in value)
                for key, value in unresolved.items()
            ):
                raise ValueError("invalid unresolved target data")
            if not all(
                isinstance(key, str) and _valid_sha(value)
                for key, value in generated_hashes.items()
            ):
                raise ValueError("invalid generated output hashes")
            return SyncState(
                raw["last_success_sha"],
                unresolved,
                raw["revision"],
                generated_hashes,
            )
        except (OSError, json.JSONDecodeError, ValueError, TypeError) as error:
            raise SyncError(f"Cannot read sync state {self.path}: {error}") from error

    def save(self, state: SyncState, expected_revision: int) -> SyncState:
        with self._exclusive_lock():
            current = self.load()
            if current.revision != expected_revision:
                raise StateConflictError(
                    f"Sync state revision changed from {expected_revision} to {current.revision}."
                )
            updated = SyncState(
                state.last_success_sha,
                {key: sorted(set(value)) for key, value in state.unresolved.items()},
                expected_revision + 1,
                dict(state.generated_hashes),
            )
            payload = {
                "version": 1,
                "revision": updated.revision,
                "last_success_sha": updated.last_success_sha,
                "unresolved": updated.unresolved,
                "generated_hashes": updated.generated_hashes,
            }
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary: str | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    "w", encoding="utf-8", dir=self.path.parent, delete=False
                ) as stream:
                    temporary = stream.name
                    json.dump(payload, stream, sort_keys=True)
                    stream.write("\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
                temporary = None
            finally:
                if temporary is not None:
                    Path(temporary).unlink(missing_ok=True)
            return updated

    @contextmanager
    def _exclusive_lock(self) -> Iterator[None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        with lock_path.open("a+b") as lock_file:
            lock_file.seek(0)
            if os.name == "nt":
                import msvcrt

                if lock_file.read(1) == b"":
                    lock_file.write(b"\0")
                    lock_file.flush()
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _valid_sha(value: object) -> bool:
    return isinstance(value, str) and len(value) in {40, 64} and all(
        char in "0123456789abcdef" for char in value
    )

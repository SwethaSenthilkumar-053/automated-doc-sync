"""Enforcement of generated-output allowlists."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .errors import PathSafetyError
from .paths import resolve_repo_path


def validate_output_paths(root: Path, changed_paths: Iterable[str], allowed_paths: Iterable[str]) -> tuple[str, ...]:
    allowed = set(allowed_paths)
    unexpected = sorted(set(changed_paths) - allowed)
    if unexpected:
        raise PathSafetyError(
            "Generator changed paths outside configured outputs: " + ", ".join(unexpected)
        )
    for path in allowed:
        resolve_repo_path(root, path)
    return tuple(sorted(set(changed_paths)))

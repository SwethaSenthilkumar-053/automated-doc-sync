"""Repository-relative path validation and mapping selection."""

from __future__ import annotations

from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Iterable

from .errors import PathSafetyError

if TYPE_CHECKING:
    from .config import Mapping


def normalize_changed_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or not value or any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise PathSafetyError(f"Invalid changed path: {value!r}")
    return path.as_posix()


def resolve_repo_path(root: Path, relative: str) -> Path:
    """Resolve a path beneath root and reject traversal through symlinks."""
    root = root.resolve()
    candidate = root.joinpath(*PurePosixPath(relative).parts)
    current = root
    for part in PurePosixPath(relative).parts:
        current = current / part
        if current.is_symlink():
            raise PathSafetyError(f"Configured path traverses a symlink: {relative}")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise PathSafetyError(f"Path escapes repository root: {relative}") from error
    return resolved


def pattern_matches(path: str, pattern: str) -> bool:
    """Match POSIX path segments with globstar matching zero or more directories."""
    path_parts = path.split("/")
    pattern_parts = pattern.split("/")
    active = {0}
    for path_part in path_parts:
        reachable = set(active)
        for pattern_index in active:
            if (
                pattern_index < len(pattern_parts)
                and pattern_parts[pattern_index] == "**"
            ):
                reachable.add(pattern_index + 1)
        following: set[int] = set()
        for pattern_index in reachable:
            if pattern_index >= len(pattern_parts):
                continue
            pattern_part = pattern_parts[pattern_index]
            if pattern_part == "**":
                following.add(pattern_index)
            elif fnmatchcase(path_part, pattern_part):
                following.add(pattern_index + 1)
        active = following
        if not active:
            return False

    pending = list(active)
    while pending:
        pattern_index = pending.pop()
        if (
            pattern_index < len(pattern_parts)
            and pattern_parts[pattern_index] == "**"
            and pattern_index + 1 not in active
        ):
            active.add(pattern_index + 1)
            pending.append(pattern_index + 1)
    return len(pattern_parts) in active


def select_mappings(
    mappings: Iterable[Mapping], changed_paths: Iterable[str]
) -> tuple[Mapping, ...]:
    normalized = tuple(normalize_changed_path(path) for path in changed_paths)
    return tuple(
        mapping
        for mapping in mappings
        if any(
            pattern_matches(path, pattern)
            for path in normalized
            for pattern in mapping.sources
        )
    )

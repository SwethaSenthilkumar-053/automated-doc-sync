"""Parsing and validation for the declarative documentation mapping."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .errors import ConfigurationError
from .paths import pattern_matches, resolve_repo_path

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_ROOT_KEYS = {"version", "mappings"}
_MAPPING_KEYS = {"id", "sources", "targets"}
_TARGET_KEYS = {"path", "kind", "generator", "markers"}
_MARKER_KEYS = {"start", "end"}


@dataclass(frozen=True)
class Target:
    path: str
    kind: str
    generator: str
    start_marker: str | None = None
    end_marker: str | None = None


@dataclass(frozen=True)
class Mapping:
    id: str
    sources: tuple[str, ...]
    targets: tuple[Target, ...]


@dataclass(frozen=True)
class SyncConfig:
    version: int
    mappings: tuple[Mapping, ...]


def _identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ConfigurationError(f"{field} must be a valid identifier.")
    return value


def _relative_path(value: Any, field: str, root: Path) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ConfigurationError(f"{field} must be a non-empty POSIX path.")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in value.split("/")):
        raise ConfigurationError(f"{field} must be repository-relative and normalized.")
    if any(":" in part for part in path.parts):
        raise ConfigurationError(f"{field} must not contain a drive prefix.")
    resolve_repo_path(root, value)
    return path.as_posix()


def _source_pattern(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or value.startswith("/")
        or ":" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise ConfigurationError(f"{field} must be a normalized relative glob.")
    return value


def parse_config(data: Any, root: Path) -> SyncConfig:
    """Validate decoded JSON data and return an immutable configuration."""
    if not isinstance(data, dict) or set(data) != _ROOT_KEYS:
        raise ConfigurationError("Configuration must contain only version and mappings.")
    if type(data["version"]) is not int or data["version"] != 1:
        raise ConfigurationError("Only mapping configuration version 1 is supported.")
    raw_mappings = data["mappings"]
    if not isinstance(raw_mappings, list):
        raise ConfigurationError("mappings must be a list.")

    mappings: list[Mapping] = []
    ids: set[str] = set()
    targets_seen: set[str] = set()
    root = root.resolve()

    for index, raw in enumerate(raw_mappings):
        label = f"mappings[{index}]"
        if not isinstance(raw, dict) or set(raw) != _MAPPING_KEYS:
            raise ConfigurationError(f"{label} must contain only id, sources, and targets.")
        mapping_id = _identifier(raw["id"], f"{label}.id")
        if mapping_id in ids:
            raise ConfigurationError(f"Duplicate mapping id: {mapping_id}")
        ids.add(mapping_id)

        sources_value = raw["sources"]
        if not isinstance(sources_value, list) or not sources_value:
            raise ConfigurationError(f"{label}.sources must be a non-empty list.")
        sources = tuple(
            _source_pattern(pattern, f"{label}.sources[{source_index}]")
            for source_index, pattern in enumerate(sources_value)
        )
        if len(set(sources)) != len(sources):
            raise ConfigurationError(f"{label}.sources contains duplicate patterns.")

        targets_value = raw["targets"]
        if not isinstance(targets_value, list) or not targets_value:
            raise ConfigurationError(f"{label}.targets must be a non-empty list.")
        targets: list[Target] = []
        for target_index, raw_target in enumerate(targets_value):
            target_label = f"{label}.targets[{target_index}]"
            if not isinstance(raw_target, dict) or not set(raw_target).issubset(_TARGET_KEYS):
                raise ConfigurationError(f"{target_label} contains unsupported fields.")
            if not {"path", "kind", "generator"}.issubset(raw_target):
                raise ConfigurationError(f"{target_label} requires path, kind, and generator.")

            target_path = _relative_path(raw_target["path"], f"{target_label}.path", root)
            if target_path in targets_seen:
                raise ConfigurationError(f"Duplicate target path: {target_path}")
            targets_seen.add(target_path)

            kind = raw_target["kind"]
            if not isinstance(kind, str) or kind not in {"markdown", "api"}:
                raise ConfigurationError(f"{target_label}.kind must be markdown or api.")
            generator = _identifier(raw_target["generator"], f"{target_label}.generator")
            markers = raw_target.get("markers")
            start_marker: str | None = None
            end_marker: str | None = None
            if kind == "markdown":
                if not isinstance(markers, dict) or set(markers) != _MARKER_KEYS:
                    raise ConfigurationError(
                        f"{target_label}.markers must contain start and end."
                    )
                start_marker, end_marker = markers["start"], markers["end"]
                if (
                    not isinstance(start_marker, str)
                    or not isinstance(end_marker, str)
                    or not start_marker.strip()
                    or not end_marker.strip()
                    or start_marker == end_marker
                    or "\n" in start_marker
                    or "\r" in start_marker
                    or "\n" in end_marker
                    or "\r" in end_marker
                ):
                    raise ConfigurationError(f"{target_label}.markers are invalid.")
            elif markers is not None:
                raise ConfigurationError(f"{target_label} must not define Markdown markers.")
            elif "markers" in raw_target:
                raise ConfigurationError(f"{target_label} must not define Markdown markers.")
            targets.append(
                Target(target_path, kind, generator, start_marker, end_marker)
            )
        mappings.append(Mapping(mapping_id, sources, tuple(targets)))

    all_sources = tuple(
        (mapping.id, pattern)
        for mapping in mappings
        for pattern in mapping.sources
    )
    for mapping in mappings:
        for target in mapping.targets:
            for source_mapping_id, pattern in all_sources:
                if _pattern_matches(target.path, pattern):
                    raise ConfigurationError(
                        f"Generated target {target.path} from mapping {mapping.id} "
                        f"is included by source mapping {source_mapping_id}."
                    )

    return SyncConfig(1, tuple(mappings))


def load_config(path: Path, root: Path) -> SyncConfig:
    try:
        with path.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
    except OSError as error:
        raise ConfigurationError(f"Cannot read mapping config {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise ConfigurationError(f"Invalid JSON in {path}: {error}") from error
    return parse_config(data, root)


def _pattern_matches(path: str, pattern: str) -> bool:
    return pattern_matches(path, pattern)

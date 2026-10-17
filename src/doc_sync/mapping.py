"""Mapping selection results and target de-duplication."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .config import Mapping, Target
from .paths import select_mappings


@dataclass(frozen=True)
class MappingSelection:
    mappings: tuple[Mapping, ...]
    targets: tuple[Target, ...]

    @property
    def is_noop(self) -> bool:
        return not self.mappings


def resolve_mappings(
    mappings: Iterable[Mapping], changed_paths: Iterable[str]
) -> MappingSelection:
    selected = select_mappings(mappings, changed_paths)
    targets: dict[str, Target] = {}
    for mapping in selected:
        for target in mapping.targets:
            targets[target.path] = target
    return MappingSelection(selected, tuple(targets.values()))

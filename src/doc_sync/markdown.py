"""Safe replacement of explicitly marked generated Markdown sections."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MarkerUpdate:
    content: str | None
    skipped_reason: str | None = None

    @property
    def changed(self) -> bool:
        return self.content is not None


def replace_marked_section(
    original: str, generated: str, start_marker: str, end_marker: str
) -> MarkerUpdate:
    lines = original.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.rstrip("\r\n") == start_marker]
    ends = [i for i, line in enumerate(lines) if line.rstrip("\r\n") == end_marker]
    if len(starts) != 1 or len(ends) != 1:
        return MarkerUpdate(None, "missing or duplicated generated-section markers")
    start, end = starts[0], ends[0]
    if start >= end:
        return MarkerUpdate(None, "generated-section markers are out of order")

    newline = "\r\n" if "\r\n" in original else "\n"
    section = generated
    if section and not section.endswith(("\n", "\r")):
        section += newline
    updated = "".join(lines[: start + 1]) + section + "".join(lines[end:])
    if updated == original:
        return MarkerUpdate(original)
    return MarkerUpdate(updated)


def update_markdown_file(
    path: Path, generated: str, start_marker: str, end_marker: str
) -> MarkerUpdate:
    try:
        original = path.read_bytes().decode("utf-8")
    except FileNotFoundError:
        return MarkerUpdate(None, "Markdown target does not exist")
    result = replace_marked_section(original, generated, start_marker, end_marker)
    if result.content is not None and result.content != original:
        path.write_bytes(result.content.encode("utf-8"))
    return result

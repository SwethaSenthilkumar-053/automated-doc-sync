"""Credential-filtered worker process for repository-local documentation generators."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .config import Target
from .generators import load_local_registry


def main(payload_json: str) -> int:
    payload = json.loads(payload_json)
    target_data = payload["target"]
    target = Target(
        target_data["path"],
        target_data["kind"],
        target_data["generator"],
        target_data["start_marker"],
        target_data["end_marker"],
    )
    registry = load_local_registry(Path(payload["root"]), payload["module"])
    content = registry.generate(
        payload["identifier"],
        Path(payload["root"]),
        target,
        tuple(payload["changed_paths"]),
    )
    sys.stdout.write(content)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.stdin.read()))
    except Exception as error:
        print(f"Generator worker failed: {error}", file=sys.stderr)
        raise SystemExit(1)

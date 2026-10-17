"""Inventory repository files relevant to documentation-sync integration decisions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


WORKFLOW_DIR = Path(".github") / "workflows"
MANIFESTS = (
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "package.json",
    "go.mod",
    "Cargo.toml",
    "Makefile",
    "tox.ini",
    "noxfile.py",
)
TOOLING_DIRS = ("scripts", "docs", "doc", "reference", "api")
IGNORED_DIRS = {".git", ".idea", ".venv", "venv", "__pycache__"}


def _relative_files(root: Path, directory: Path) -> list[str]:
    target = root / directory
    if not target.is_dir():
        return []

    return sorted(
        path.relative_to(root).as_posix()
        for path in target.rglob("*")
        if path.is_file()
        and not any(part in IGNORED_DIRS for part in path.relative_to(root).parts)
    )


def inspect_repository(root: Path) -> dict[str, Any]:
    root = root.resolve()
    workflow_files = [
        name
        for name in _relative_files(root, WORKFLOW_DIR)
        if Path(name).suffix.lower() in {".yml", ".yaml"}
    ]
    tooling_files = sorted(
        {
            name
            for directory in TOOLING_DIRS
            for name in _relative_files(root, Path(directory))
        }
    )
    manifest_files = [
        name for name in MANIFESTS if (root / name).is_file()
    ]

    return {
        "repository_root": str(root),
        "local_evidence": {
            "github_workflows": workflow_files,
            "project_manifests_and_task_runners": manifest_files,
            "documentation_or_script_files": tooling_files,
        },
        "findings": {
            "workflow_and_ci_conventions": (
                "not_found" if not workflow_files else "inspect listed workflows"
            ),
            "automation_identity_and_permissions": "requires_github_settings_confirmation",
            "branch_protection_and_commit_signing": "requires_github_settings_confirmation",
            "markdown_and_api_generators": (
                "not_found" if not tooling_files else "inspect listed files"
            ),
            "documentation_checks_and_tests": (
                "not_found"
                if not manifest_files and not workflow_files
                else "inspect listed manifests and workflows"
            ),
            "notification_destination": "requires_owner_confirmation",
            "workflow_timeout_and_artifact_retention": "requires_github_settings_confirmation",
            "partial_failure_and_unresolved_mapping_policy": "requires_design_decision",
            "manual_rerun_and_durable_checkpoint_policy": "requires_design_decision",
            "coalescing_and_pr_audit_recovery_policy": "requires_design_decision",
        },
        "external_confirmation_required": [
            "Existing automation identity, permissions, and branch protection",
            "Commit-signing requirements",
            "Approved notification destination",
            "Workflow timeout and artifact/log retention policy",
        ],
        "design_decisions_required": [
            "Durable processing checkpoint and recovery after a commit/state-update failure",
            "How skipped marker targets remain visible and can be retried",
            "Manual rerun target and checkpoint semantics",
            "How coalesced merge events retain changed paths and PR audit references",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inventory local evidence for documentation-sync integration contracts."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repository root to inspect (defaults to the parent of src).",
    )
    args = parser.parse_args()
    print(json.dumps(inspect_repository(args.root), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

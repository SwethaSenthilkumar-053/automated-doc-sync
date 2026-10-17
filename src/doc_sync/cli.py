"""Command-line entry point for local, credential-free documentation sync."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path
import subprocess
import math
import re

from .audit import AuditRecord
from .config import load_config
from .errors import SyncError
from .generators import GeneratorRegistry, IsolatedGeneratorRegistry, load_registry
from .git import (
    changed_paths,
    ensure_clean_targets,
    head_sha,
    working_tree_snapshot,
)
from .mapping import MappingSelection, resolve_mappings
from .markdown import update_markdown_file
from .notify import LoggingNotifier
from .outputs import validate_output_paths
from .paths import resolve_repo_path
from .retry import run_with_retries
from .state import StateStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Synchronize configured local documentation.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, default=Path("docs-sync.json"))
    parser.add_argument("--state", type=Path, default=Path(".doc-sync-state.json"))
    parser.add_argument("--audit", type=Path, default=Path("doc-sync-audit.json"))
    parser.add_argument("--target-sha", help="Process through this commit instead of current HEAD.")
    parser.add_argument("--pr-number", type=int, action="append", default=[])
    parser.add_argument(
        "--generator-module",
        help="Repository-local trusted Python module defining register_generators(registry).",
    )
    parser.add_argument(
        "--check",
        action="append",
        default=[],
        metavar="JSON_ARGV",
        help='Validation argv as JSON, e.g. \'["python", "-m", "pytest"]\'; repeat as needed.',
    )
    parser.add_argument("--check-timeout", type=float, default=900)
    parser.add_argument("--validate-only", action="store_true")
    return parser


def run(
    args: argparse.Namespace,
    registry: GeneratorRegistry | IsolatedGeneratorRegistry | None = None,
) -> int:
    root = args.root.resolve()
    config_path = args.config if args.config.is_absolute() else root / args.config
    state_path = args.state if args.state.is_absolute() else root / args.state
    audit_path = args.audit if args.audit.is_absolute() else root / args.audit
    record = AuditRecord()
    notifier = LoggingNotifier()
    try:
        if any(number <= 0 for number in args.pr_number):
            raise SyncError("Pull request numbers must be positive integers.")
        config = load_config(config_path, root)
        record.triggering_prs = args.pr_number
        if args.validate_only:
            return 0

        store = StateStore(state_path)
        state = store.load()
        current_head = args.target_sha or head_sha(root)
        if args.target_sha and (
            re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", args.target_sha) is None
            or not _is_commit(root, args.target_sha)
        ):
            raise SyncError(f"Target SHA is not a valid commit: {args.target_sha}")

        if state.last_success_sha:
            paths = changed_paths(root, state.last_success_sha, current_head)
        else:
            paths = changed_paths(root, _root_commit(root), current_head)
        record.changed_paths = list(paths)

        changed_selection = resolve_mappings(config.mappings, paths)
        pending_ids = set(state.unresolved)
        pending_mappings = tuple(
            mapping for mapping in config.mappings if mapping.id in pending_ids
        )
        selected_ids = {mapping.id for mapping in changed_selection.mappings}
        selected_ids.update(mapping.id for mapping in pending_mappings)
        selected_mappings = tuple(
            mapping for mapping in config.mappings if mapping.id in selected_ids
        )
        targets_by_path = {
            target.path: target
            for mapping in selected_mappings
            for target in mapping.targets
        }
        selection = MappingSelection(selected_mappings, tuple(targets_by_path.values()))
        if selection.is_noop:
            record.complete("no-op")
            record.write(audit_path)
            state.last_success_sha = current_head
            store.save(state, state.revision)
            return 0

        active_registry = registry or load_registry(root, args.generator_module)
        ensure_clean_targets(
            root,
            (target.path for target in selection.targets),
            state.generated_hashes,
        )
        before = working_tree_snapshot(root)
        failures: list[str] = []
        generated_paths: list[str] = []
        for mapping in selection.mappings:
            for target in mapping.targets:
                target_path = resolve_repo_path(root, target.path)
                try:
                    content = run_with_retries(
                        lambda: active_registry.generate(
                            target.generator, root, target, paths
                        )
                    )
                    if target.kind == "markdown":
                        assert target.start_marker is not None and target.end_marker is not None
                        update = update_markdown_file(
                            target_path, content, target.start_marker, target.end_marker
                        )
                        if update.skipped_reason:
                            failures.append(f"{mapping.id}:{target.path}: {update.skipped_reason}")
                            continue
                    else:
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        target_path.write_text(content, encoding="utf-8", newline="")
                    generated_paths.append(target.path)
                except SyncError as error:
                    failures.append(f"{mapping.id}:{target.path}: {error}")

        _run_checks(root, args.check, args.check_timeout)
        after = working_tree_snapshot(root)
        changed_worktree = {
            path
            for path in set(before) | set(after)
            if before.get(path) != after.get(path)
        }
        record.generated_paths = sorted(changed_worktree)
        validate_output_paths(root, changed_worktree, (target.path for target in selection.targets))

        # Preserve unresolved targets so a future run can retry them even after
        # later source changes are checkpointed.
        unresolved = dict(state.unresolved)
        for mapping in selection.mappings:
            mapping_failures = [
                item for item in failures if item.startswith(f"{mapping.id}:")
            ]
            if mapping_failures:
                unresolved[mapping.id] = sorted(
                    {item.split(":", 1)[1].split(":", 1)[0] for item in mapping_failures}
                )
            else:
                unresolved.pop(mapping.id, None)
        state.unresolved = unresolved
        for target in selection.targets:
            target_path = root / target.path
            if target_path.is_file() and not target_path.is_symlink():
                state.generated_hashes[target.path] = hashlib.sha256(
                    target_path.read_bytes()
                ).hexdigest()
        state.last_success_sha = current_head

        if failures:
            record.details.extend(failures)
            record.complete("partial")
            notifier.notify("Documentation sync partially completed", "\n".join(failures))
        else:
            record.complete("success")
        record.write(audit_path)
        store.save(state, state.revision)
        return 2 if failures else 0
    except Exception as error:
        record.details.append(str(error))
        record.complete("failed")
        record.write(audit_path)
        notifier.notify("Documentation sync failed", str(error))
        if isinstance(error, SyncError):
            logging.error("%s", error)
            return 1
        raise


def _is_commit(root: Path, sha: str) -> bool:
    import subprocess

    return subprocess.run(
        ["git", "-C", str(root), "cat-file", "-e", f"{sha}^{{commit}}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


def _root_commit(root: Path) -> str:
    import subprocess

    result = subprocess.run(
        ["git", "-C", str(root), "rev-list", "--max-parents=0", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode or not result.stdout.strip():
        raise SyncError("Unable to determine repository root commit.")
    return result.stdout.splitlines()[0]


def _run_checks(root: Path, commands: list[str], timeout: float) -> None:
    if not math.isfinite(timeout) or timeout <= 0:
        raise SyncError("Check timeout must be positive.")
    for command in commands:
        try:
            argv = json.loads(command)
        except json.JSONDecodeError as error:
            raise SyncError(f"Validation command must be JSON argv: {error}") from error
        if (
            not isinstance(argv, list)
            or not argv
            or any(not isinstance(part, str) or not part for part in argv)
        ):
            raise SyncError("Validation command must be a non-empty JSON array of strings.")
        try:
            result = subprocess.run(
                argv,
                cwd=root,
                check=False,
                shell=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as error:
            raise SyncError(
                f"Validation command exceeded its {timeout:g}s timeout."
            ) from error
        except OSError as error:
            raise SyncError(f"Could not start validation command {argv[0]!r}: {error}") from error
        if result.returncode:
            raise SyncError(
                f"Validation command {argv[0]!r} exited with status {result.returncode}."
            )

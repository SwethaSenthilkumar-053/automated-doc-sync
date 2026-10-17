"""Git helpers with explicit base verification and targeted local commits."""

from __future__ import annotations

import subprocess
import hashlib
from pathlib import Path
from typing import Iterable

from .errors import ConcurrentUpdateError, SyncError


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and result.returncode:
        raise SyncError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result


def head_sha(root: Path) -> str:
    return _git(root, "rev-parse", "HEAD").stdout.strip()


def is_ancestor(root: Path, base_sha: str, head: str = "HEAD") -> bool:
    return _git(root, "merge-base", "--is-ancestor", base_sha, head, check=False).returncode == 0


def changed_paths(root: Path, base_sha: str, head: str = "HEAD") -> tuple[str, ...]:
    if not is_ancestor(root, base_sha, head):
        raise SyncError(f"Checkpoint {base_sha} is not an ancestor of {head}.")
    output = _git(root, "diff", "--name-only", "--no-renames", "-z", base_sha, head).stdout
    return tuple(sorted({path for path in output.split("\0") if path}))


def working_tree_paths(root: Path) -> tuple[str, ...]:
    output = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout
    paths: set[str] = set()
    entries = output.split("\0")
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        path = entry[3:]
        if entry[:2].find("R") >= 0 or entry[:2].find("C") >= 0:
            if index < len(entries):
                index += 1
        paths.add(path.replace("\\", "/"))
    return tuple(sorted(paths))


def working_tree_snapshot(root: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for relative in working_tree_paths(root):
        path = root / relative
        if path.is_symlink():
            value = "symlink:" + str(path.readlink())
        elif not path.exists():
            value = "missing"
        elif path.is_file():
            value = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            value = "other"
        snapshot[relative] = value
    return snapshot


def ensure_clean_targets(
    root: Path,
    targets: Iterable[str],
    generated_hashes: dict[str, str] | None = None,
) -> None:
    generated_hashes = generated_hashes or {}
    dirty = set(working_tree_paths(root))
    conflicts = []
    for relative in dirty.intersection(targets):
        path = root / relative
        if path.is_symlink() or not path.is_file():
            conflicts.append(relative)
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if generated_hashes.get(relative) != digest:
            conflicts.append(relative)
    if conflicts:
        raise SyncError(
            "Refusing to overwrite pre-existing changes in targets: "
            + ", ".join(sorted(conflicts))
        )


def commit_outputs(
    root: Path, expected_base_sha: str, paths: Iterable[str], message: str
) -> str | None:
    if head_sha(root) != expected_base_sha:
        raise ConcurrentUpdateError("Default-branch base moved before commit; regenerate outputs.")
    selected = tuple(sorted(set(paths)))
    if not selected:
        return None
    if not message.strip():
        raise SyncError("Commit message must not be empty.")
    staged = _git(
        root, "diff", "--cached", "--name-only", "--no-renames", "-z"
    ).stdout
    staged_paths = {path for path in staged.split("\0") if path}
    unrelated_staged = staged_paths - set(selected)
    if unrelated_staged:
        raise SyncError(
            "Refusing to include pre-staged paths outside generated outputs: "
            + ", ".join(sorted(unrelated_staged))
        )
    _git(root, "add", "--", *selected)
    staged_after = _git(
        root, "diff", "--cached", "--name-only", "--no-renames", "-z"
    ).stdout
    staged_paths_after = {path for path in staged_after.split("\0") if path}
    if staged_paths_after - set(selected):
        raise SyncError("Staging generated outputs would include unrelated paths.")
    cached_diff = _git(root, "diff", "--cached", "--quiet", check=False)
    if cached_diff.returncode == 0:
        return None
    if cached_diff.returncode != 1:
        raise SyncError(f"Unable to inspect staged output diff: {cached_diff.stderr.strip()}")
    _git(root, "commit", "-m", message)
    return head_sha(root)


def push_current_branch(root: Path) -> None:
    raise SyncError(
        "Remote push is intentionally not implemented: configure the approved "
        "automation identity and branch-protection integration first."
    )

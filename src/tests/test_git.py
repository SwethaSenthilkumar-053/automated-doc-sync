import subprocess

import pytest

from doc_sync.errors import ConcurrentUpdateError, SyncError
from doc_sync.git import (
    changed_paths,
    commit_outputs,
    ensure_clean_targets,
    head_sha,
    working_tree_paths,
)
from doc_sync.errors import SyncError
import hashlib


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def init_repo(root):
    git(root, "init")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "config", "user.name", "Test")
    (root / "source.py").write_text("one\n", encoding="utf-8")
    git(root, "add", "source.py")
    git(root, "commit", "-m", "initial")


def test_changed_paths_and_commit_only_allowed_file(tmp_path):
    init_repo(tmp_path)
    base = head_sha(tmp_path)
    (tmp_path / "source.py").write_text("two\n", encoding="utf-8")
    git(tmp_path, "commit", "-am", "source change")
    assert changed_paths(tmp_path, base) == ("source.py",)

    expected_base = head_sha(tmp_path)
    (tmp_path / "docs.md").write_text("generated\n", encoding="utf-8")
    commit = commit_outputs(tmp_path, expected_base, ["docs.md"], "docs: update")
    assert commit == head_sha(tmp_path)
    assert commit != expected_base


def test_commit_refuses_stale_base(tmp_path):
    init_repo(tmp_path)
    base = head_sha(tmp_path)
    (tmp_path / "source.py").write_text("two\n", encoding="utf-8")
    git(tmp_path, "commit", "-am", "source change")
    with pytest.raises(ConcurrentUpdateError):
        commit_outputs(tmp_path, base, ["docs.md"], "docs: update")


def test_commit_does_not_include_pre_staged_unrelated_paths(tmp_path):
    init_repo(tmp_path)
    base = head_sha(tmp_path)
    (tmp_path / "unrelated.txt").write_text("keep staged\n", encoding="utf-8")
    (tmp_path / "docs.md").write_text("generated\n", encoding="utf-8")
    git(tmp_path, "add", "unrelated.txt")
    with pytest.raises(SyncError, match="pre-staged paths"):
        commit_outputs(tmp_path, base, ["docs.md"], "docs: update")
    assert head_sha(tmp_path) == base


def test_commit_skips_unchanged_output(tmp_path):
    init_repo(tmp_path)
    base = head_sha(tmp_path)
    assert commit_outputs(tmp_path, base, ["source.py"], "docs: no-op") is None
    assert head_sha(tmp_path) == base


def test_working_tree_paths_includes_untracked(tmp_path):
    init_repo(tmp_path)
    (tmp_path / "untracked.md").write_text("x", encoding="utf-8")
    assert working_tree_paths(tmp_path) == ("untracked.md",)


def test_clean_target_guard_allows_only_previously_generated_content(tmp_path):
    init_repo(tmp_path)
    target = tmp_path / "source.py"
    target.write_text("generated\n", encoding="utf-8")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    ensure_clean_targets(tmp_path, ["source.py"], {"source.py": digest})
    with pytest.raises(SyncError, match="Refusing to overwrite"):
        ensure_clean_targets(tmp_path, ["source.py"], {"source.py": "0" * 64})


def test_checkpoint_must_be_ancestor(tmp_path):
    init_repo(tmp_path)
    with pytest.raises(SyncError, match="not an ancestor"):
        changed_paths(tmp_path, "f" * 40)

import json
import subprocess
from pathlib import Path
import sys

from doc_sync.cli import build_parser, run
from doc_sync.config import Target
from doc_sync.generators import GeneratorRegistry


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def make_repo(root: Path) -> Path:
    git(root, "init")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "config", "user.name", "Test")
    (root / "src").mkdir()
    (root / "docs").mkdir()
    (root / "src" / "module.py").write_text("value = 1\n", encoding="utf-8")
    (root / "docs" / "api.md").write_text(
        "Manual\n<!-- generated:start -->\nold\n<!-- generated:end -->\n",
        encoding="utf-8",
    )
    config = {
        "version": 1,
        "mappings": [
            {
                "id": "api",
                "sources": ["src/**/*.py"],
                "targets": [
                    {
                        "path": "docs/api.md",
                        "kind": "markdown",
                        "generator": "api",
                        "markers": {
                            "start": "<!-- generated:start -->",
                            "end": "<!-- generated:end -->",
                        },
                    }
                ],
            }
        ],
    }
    (root / "docs-sync.json").write_text(json.dumps(config), encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-m", "initial")
    (root / "src" / "module.py").write_text("value = 2\n", encoding="utf-8")
    git(root, "commit", "-am", "update source")
    return root


def test_cli_updates_mapped_markdown_and_records_audit(tmp_path):
    root = make_repo(tmp_path)
    args = build_parser().parse_args(
        [
            "--root",
            str(root),
            "--config",
            "docs-sync.json",
            "--state",
            ".state.json",
            "--audit",
            "audit.json",
            "--pr-number",
            "44",
        ]
    )
    registry = GeneratorRegistry()
    registry.register("api", lambda repo, target, paths: "Generated API")

    assert run(args, registry) == 0
    content = (root / "docs" / "api.md").read_text(encoding="utf-8")
    assert content == (
        "Manual\n<!-- generated:start -->\nGenerated API\n"
        "<!-- generated:end -->\n"
    )
    audit = json.loads((root / "audit.json").read_text(encoding="utf-8"))
    assert audit["outcome"] == "success"
    assert audit["triggering_prs"] == [44]
    assert audit["generated_paths"] == ["docs/api.md"]


def test_cli_records_missing_markers_as_partial_and_retries_unresolved(tmp_path):
    root = make_repo(tmp_path)
    (root / "docs" / "api.md").write_text("No generated markers.\n", encoding="utf-8")
    git(root, "add", "docs/api.md")
    git(root, "commit", "-m", "remove generated markers")
    args = build_parser().parse_args(
        [
            "--root",
            str(root),
            "--config",
            "docs-sync.json",
            "--state",
            ".state.json",
            "--audit",
            "audit.json",
        ]
    )
    registry = GeneratorRegistry()
    registry.register("api", lambda repo, target, paths: "Generated API")

    assert run(args, registry) == 2
    state = json.loads((root / ".state.json").read_text(encoding="utf-8"))
    assert state["unresolved"] == {"api": ["docs/api.md"]}
    assert state["last_success_sha"]

    # A later run retries unresolved mappings even with no new source commit.
    assert run(args, registry) == 2


def test_cli_dry_run_does_not_commit(tmp_path):
    root = make_repo(tmp_path)
    before = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    args = build_parser().parse_args(
        [
            "--root",
            str(root),
            "--config",
            "docs-sync.json",
            "--state",
            ".state.json",
            "--audit",
            "audit.json",
        ]
    )
    registry = GeneratorRegistry()
    registry.register("api", lambda repo, target, paths: "Generated API")
    assert run(args, registry) == 0
    after = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    assert after == before


def test_cli_can_reprocess_its_previous_generated_output(tmp_path):
    root = make_repo(tmp_path)
    args = build_parser().parse_args(
        [
            "--root",
            str(root),
            "--config",
            "docs-sync.json",
            "--state",
            ".state.json",
            "--audit",
            "audit.json",
        ]
    )
    registry = GeneratorRegistry()
    registry.register("api", lambda repo, target, paths: "First output")
    assert run(args, registry) == 0

    (root / "src" / "module.py").write_text("value = 3\n", encoding="utf-8")
    git(root, "add", "src/module.py")
    git(root, "commit", "-m", "second source update")
    registry = GeneratorRegistry()
    registry.register("api", lambda repo, target, paths: "Second output")
    assert run(args, registry) == 0
    assert "Second output" in (root / "docs" / "api.md").read_text(encoding="utf-8")


def test_cli_runs_json_argv_checks_without_shell(tmp_path):
    root = make_repo(tmp_path)
    args = build_parser().parse_args(
        [
            "--root",
            str(root),
            "--config",
            "docs-sync.json",
            "--state",
            ".state.json",
            "--audit",
            "audit.json",
            "--check",
            json.dumps([sys.executable, "-c", "pass"]),
        ]
    )
    registry = GeneratorRegistry()
    registry.register("api", lambda repo, target, paths: "Generated API")
    assert run(args, registry) == 0

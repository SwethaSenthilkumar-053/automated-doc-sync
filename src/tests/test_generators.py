from pathlib import Path
import sys

import pytest

from doc_sync.config import Target
from doc_sync.errors import GeneratorError, PathSafetyError
from doc_sync.generators import GeneratorRegistry, load_registry


def test_registry_runs_only_explicitly_registered_generators(tmp_path):
    registry = GeneratorRegistry()
    target = Target("docs/api.md", "api", "trusted")
    registry.register("trusted", lambda root, item, changed: "content")
    assert registry.generate("trusted", tmp_path, target, ("src/a.py",)) == "content"


def test_unregistered_generator_is_terminal_error(tmp_path):
    with pytest.raises(GeneratorError, match="No trusted local generator"):
        GeneratorRegistry().generate(
            "arbitrary", tmp_path, Target("docs/api.md", "api", "arbitrary"), ()
        )


def test_generator_must_return_text(tmp_path):
    registry = GeneratorRegistry()
    registry.register("bad", lambda root, target, changed: Path("unexpected"))
    with pytest.raises(GeneratorError, match="must return text"):
        registry.generate("bad", tmp_path, Target("docs/api.md", "api", "bad"), ())


def test_command_generator_uses_argv_without_a_shell(tmp_path):
    registry = GeneratorRegistry()
    registry.register_command(
        "fixed",
        (
            sys.executable,
            "-c",
            "import sys; print(sys.argv[1])",
            "{target}",
        ),
        5,
    )
    result = registry.generate(
        "fixed",
        tmp_path,
        Target("docs/space path.md", "api", "fixed"),
        (),
    )
    assert result.strip() == "docs/space path.md"


def test_loads_repository_local_generator_module(tmp_path):
    module = tmp_path / "generator.py"
    module.write_text(
        "def register_generators(registry):\n"
        "    registry.register('sample', lambda root, target, paths: 'ok')\n",
        encoding="utf-8",
    )
    registry = load_registry(tmp_path, "generator.py")
    assert registry.generate(
        "sample", tmp_path, Target("docs/a.md", "api", "sample"), ()
    ) == "ok"


def test_isolated_generator_does_not_receive_unapproved_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("DOC_SYNC_PRIVATE_TOKEN", "must-not-be-inherited")
    module = tmp_path / "generator.py"
    module.write_text(
        "import os\n"
        "def register_generators(registry):\n"
        "    registry.register('env', lambda root, target, paths: "
        "os.environ.get('DOC_SYNC_PRIVATE_TOKEN', 'filtered'))\n",
        encoding="utf-8",
    )
    registry = load_registry(tmp_path, "generator.py")
    assert registry.generate(
        "env", tmp_path, Target("docs/a.md", "api", "env"), ()
    ) == "filtered"


def test_rejects_generator_module_symlink_escape(tmp_path):
    outside = tmp_path.parent / (tmp_path.name + "-outside.py")
    outside.write_text("def register_generators(registry): pass\n", encoding="utf-8")
    link = tmp_path / "generator.py"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Symlink creation is unavailable.")
    with pytest.raises(PathSafetyError, match="symlink"):
        load_registry(tmp_path, "generator.py")

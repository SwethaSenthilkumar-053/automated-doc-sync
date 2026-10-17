"""Allowlisted local generator registry and isolated worker support.

Generator implementations are trusted Python code registered by the application.
The mapping file can select an identifier, but cannot supply shell commands.
"""

from __future__ import annotations

import subprocess
import math
import importlib.util
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from .config import Target
from .errors import GeneratorError, TransientSyncError
from .paths import resolve_repo_path


class Generator(Protocol):
    def __call__(self, root: Path, target: Target, changed_paths: tuple[str, ...]) -> str:
        """Generate the content for a single configured target."""


class GeneratorRegistry:
    def __init__(self) -> None:
        self._generators: dict[str, Generator] = {}
        self._commands: dict[str, tuple[tuple[str, ...], float]] = {}

    def register(self, identifier: str, generator: Generator) -> None:
        if not identifier or identifier in self._generators or identifier in self._commands:
            raise ValueError(f"Generator identifier is empty or already registered: {identifier}")
        self._generators[identifier] = generator

    def register_command(
        self, identifier: str, command: tuple[str, ...], timeout_seconds: float
    ) -> None:
        """Register a fixed, trusted argv template; mappings cannot provide commands."""
        if (
            not identifier
            or identifier in self._generators
            or identifier in self._commands
            or not command
            or any(not isinstance(part, str) or not part for part in command)
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("Invalid or duplicate trusted generator command.")
        self._commands[identifier] = (command, timeout_seconds)

    def generate(
        self, identifier: str, root: Path, target: Target, changed_paths: tuple[str, ...]
    ) -> str:
        generator = self._generators.get(identifier)
        command_spec = self._commands.get(identifier)
        if generator is None and command_spec is None:
            raise GeneratorError(f"No trusted local generator is registered as {identifier!r}.")
        if command_spec is not None:
            command, timeout = command_spec
            args = [
                part.replace("{root}", str(root))
                .replace("{target}", target.path)
                .replace("{changed_paths}", ";".join(changed_paths))
                for part in command
            ]
            try:
                result = subprocess.run(
                    args,
                    cwd=root,
                    check=False,
                    shell=False,
                    text=True,
                    encoding="utf-8",
                    capture_output=True,
                    timeout=timeout,
                    env=_generator_environment(),
                )
            except subprocess.TimeoutExpired as error:
                raise TransientSyncError(
                    f"Generator {identifier!r} exceeded its {timeout:g}s timeout."
                ) from error
            except OSError as error:
                raise GeneratorError(f"Could not start generator {identifier!r}: {error}") from error
            if result.returncode:
                raise GeneratorError(
                    f"Generator {identifier!r} exited with status {result.returncode}."
                )
            content = result.stdout
        else:
            assert generator is not None
            content = generator(root, target, changed_paths)
        if not isinstance(content, str):
            raise GeneratorError(f"Generator {identifier!r} must return text.")
        return content


def callable_generator(
    function: Callable[[Path, Target, tuple[str, ...]], str]
) -> Generator:
    """Explicit typing adapter for trusted generator functions."""
    return function


def load_registry(
    root: Path, module_path: str | None
) -> GeneratorRegistry | IsolatedGeneratorRegistry:
    """Create a credential-filtered subprocess runner for a local module."""
    if module_path is None:
        return GeneratorRegistry()
    path = resolve_repo_path(root, module_path)
    if not path.is_file() or path.suffix != ".py":
        raise GeneratorError("Generator module must be an existing repository-local .py file.")
    return IsolatedGeneratorRegistry(root.resolve(), module_path)


def load_local_registry(root: Path, module_path: str) -> GeneratorRegistry:
    """Import a generator module in the filtered worker process."""
    registry = GeneratorRegistry()
    path = resolve_repo_path(root, module_path)
    if not path.is_file() or path.suffix != ".py":
        raise GeneratorError("Generator module must be an existing repository-local .py file.")
    spec = importlib.util.spec_from_file_location("doc_sync_project_generators", path)
    if spec is None or spec.loader is None:
        raise GeneratorError(f"Could not load generator module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    register = getattr(module, "register_generators", None)
    if not callable(register):
        raise GeneratorError(
            f"Generator module {module_path!r} must define register_generators(registry)."
        )
    register(registry)
    return registry


class IsolatedGeneratorRegistry:
    def __init__(self, root: Path, module_path: str, timeout_seconds: float = 900) -> None:
        self.root = root
        self.module_path = module_path
        self.timeout_seconds = timeout_seconds

    def generate(
        self, identifier: str, root: Path, target: Target, changed_paths: tuple[str, ...]
    ) -> str:
        payload = json.dumps(
            {
                "root": str(self.root),
                "module": self.module_path,
                "identifier": identifier,
                "target": {
                    "path": target.path,
                    "kind": target.kind,
                    "generator": target.generator,
                    "start_marker": target.start_marker,
                    "end_marker": target.end_marker,
                },
                "changed_paths": changed_paths,
            }
        )
        environment = _generator_environment()
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        try:
            result = subprocess.run(
                [sys.executable, "-m", "doc_sync.worker"],
                cwd=self.root,
                check=False,
                shell=False,
                text=True,
                encoding="utf-8",
                capture_output=True,
                timeout=self.timeout_seconds,
                env=environment,
                input=payload,
            )
        except subprocess.TimeoutExpired as error:
            raise TransientSyncError(
                f"Generator {identifier!r} exceeded its {self.timeout_seconds:g}s timeout."
            ) from error
        except OSError as error:
            raise GeneratorError(
                f"Could not start isolated generator {identifier!r}: {error}"
            ) from error
        if result.returncode:
            raise GeneratorError(
                f"Isolated generator {identifier!r} exited with status {result.returncode}."
            )
        return result.stdout


def _generator_environment() -> dict[str, str]:
    allowed = {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "TMPDIR",
        "HOME",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "LANG",
        "LC_ALL",
    }
    environment = {
        key: value for key, value in os.environ.items() if key.upper() in allowed
    }
    environment.update(
        {
            "PYTHONNOUSERSITE": "1",
            "PYTHONIOENCODING": "utf-8",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "never",
        }
    )
    return environment

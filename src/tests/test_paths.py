import pytest

from doc_sync.errors import PathSafetyError
from doc_sync.paths import normalize_changed_path, pattern_matches, resolve_repo_path


def test_normalizes_windows_separator():
    assert normalize_changed_path("src\\module.py") == "src/module.py"


@pytest.mark.parametrize("value", ["../secret", "/etc/passwd", "src/../secret", ""])
def test_rejects_unsafe_changed_paths(value):
    with pytest.raises(PathSafetyError):
        normalize_changed_path(value)


def test_rejects_symlink_escape(tmp_path):
    outside = tmp_path.parent / (tmp_path.name + "-outside")
    outside.mkdir()
    root = tmp_path / "repo"
    root.mkdir()
    try:
        (root / "linked").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation is unavailable.")
    with pytest.raises(PathSafetyError):
        resolve_repo_path(root, "linked/target.md")


def test_globstar_matches_zero_or_more_directories():
    assert pattern_matches("src/app.py", "src/**/*.py")
    assert pattern_matches("src/package/app.py", "src/**/*.py")
    assert not pattern_matches("other/app.py", "src/**/*.py")

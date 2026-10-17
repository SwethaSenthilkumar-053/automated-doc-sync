import pytest

from doc_sync.errors import PathSafetyError
from doc_sync.outputs import validate_output_paths


def test_accepts_changes_in_configured_outputs(tmp_path):
    assert validate_output_paths(tmp_path, ["docs/api.md"], ["docs/api.md"]) == (
        "docs/api.md",
    )


def test_rejects_unlisted_output(tmp_path):
    with pytest.raises(PathSafetyError, match="outside configured"):
        validate_output_paths(tmp_path, ["docs/unmapped.md"], ["docs/api.md"])

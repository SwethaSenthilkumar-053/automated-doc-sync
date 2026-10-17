import json

import pytest

from doc_sync.errors import StateConflictError, SyncError
from doc_sync.state import StateStore, SyncState


def test_saves_state_atomically_and_tracks_unresolved(tmp_path):
    store = StateStore(tmp_path / "state.json")
    saved = store.save(
        SyncState("a" * 40, {"mapping": ["docs/a.md"]}),
        expected_revision=0,
    )
    assert saved.revision == 1
    loaded = store.load()
    assert loaded.last_success_sha == "a" * 40
    assert loaded.unresolved == {"mapping": ["docs/a.md"]}


def test_round_trips_generated_output_hashes(tmp_path):
    store = StateStore(tmp_path / "state.json")
    saved = store.save(SyncState(generated_hashes={"docs/a.md": "b" * 64}), 0)
    assert store.load().generated_hashes == {"docs/a.md": "b" * 64}
    assert saved.revision == 1


def test_detects_stale_state_write(tmp_path):
    store = StateStore(tmp_path / "state.json")
    store.save(SyncState("a" * 40), expected_revision=0)
    with pytest.raises(StateConflictError):
        store.save(SyncState("b" * 40), expected_revision=0)


def test_rejects_corrupt_state(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"version": 9}), encoding="utf-8")
    with pytest.raises(SyncError, match="Cannot read sync state"):
        StateStore(path).load()

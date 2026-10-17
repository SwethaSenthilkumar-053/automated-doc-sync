from doc_sync.config import Mapping, Target
from doc_sync.mapping import resolve_mappings


def test_selects_and_deduplicates_targets():
    target = Target("docs/api.md", "api", "api-gen")
    mappings = (
        Mapping("a", ("src/a/*.py",), (target,)),
        Mapping("b", ("src/b/*.py",), (target,)),
    )
    selected = resolve_mappings(mappings, ("src/a/app.py", "unrelated.txt"))
    assert [item.id for item in selected.mappings] == ["a"]
    assert selected.targets == (target,)


def test_unmapped_paths_are_noop():
    mapping = Mapping("a", ("src/*.py",), (Target("docs/api.md", "api", "api-gen"),))
    assert resolve_mappings((mapping,), ("README.md",)).is_noop

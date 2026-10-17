import pytest

from doc_sync.markdown import replace_marked_section, update_markdown_file


def test_replaces_only_marked_content_and_preserves_manual_text():
    original = "before\n<!-- start -->\nold\n<!-- end -->\nafter\n"
    result = replace_marked_section(original, "new", "<!-- start -->", "<!-- end -->")
    assert result.content == "before\n<!-- start -->\nnew\n<!-- end -->\nafter\n"


def test_preserves_crlf():
    original = "before\r\n<!-- start -->\r\nold\r\n<!-- end -->\r\nafter\r\n"
    result = replace_marked_section(original, "new", "<!-- start -->", "<!-- end -->")
    assert result.content == "before\r\n<!-- start -->\r\nnew\r\n<!-- end -->\r\nafter\r\n"


@pytest.mark.parametrize(
    "original",
    [
        "no markers",
        "<!-- start -->\n<!-- start -->\n<!-- end -->",
        "<!-- end -->\n<!-- start -->",
    ],
)
def test_skips_missing_or_malformed_markers(original):
    result = replace_marked_section(original, "new", "<!-- start -->", "<!-- end -->")
    assert result.content is None
    assert result.skipped_reason


def test_file_update_writes_only_valid_result(tmp_path):
    path = tmp_path / "docs.md"
    path.write_text("<!-- start -->\nold\n<!-- end -->\n", encoding="utf-8")
    result = update_markdown_file(path, "new", "<!-- start -->", "<!-- end -->")
    assert result.changed
    assert "new\n" in path.read_text(encoding="utf-8")

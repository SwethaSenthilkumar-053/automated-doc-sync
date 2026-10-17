import pytest
from pathlib import Path

from doc_sync.config import load_config, parse_config
from doc_sync.errors import ConfigurationError, PathSafetyError


def config_for(target="docs/reference.md"):
    return {
        "version": 1,
        "mappings": [
            {
                "id": "python-api",
                "sources": ["src/**/*.py"],
                "targets": [
                    {
                        "path": target,
                        "kind": "markdown",
                        "generator": "api-docs",
                        "markers": {"start": "<!-- generated:start -->", "end": "<!-- generated:end -->"},
                    }
                ],
            }
        ],
    }


def test_parses_valid_mapping(tmp_path):
    parsed = parse_config(config_for(), tmp_path)
    assert parsed.mappings[0].id == "python-api"
    assert parsed.mappings[0].targets[0].kind == "markdown"


def test_parses_sample_configuration_fixture(tmp_path):
    fixture = Path(__file__).parent / "fixtures" / "docs-sync.json"
    parsed = load_config(fixture, tmp_path)
    assert parsed.mappings[0].id == "sample-api"


@pytest.mark.parametrize("target", ["../outside.md", "/absolute.md", "C:/outside.md", "docs//ref.md"])
def test_rejects_unsafe_or_non_normalized_targets(tmp_path, target):
    with pytest.raises((ConfigurationError, PathSafetyError)):
        parse_config(config_for(target), tmp_path)


def test_rejects_duplicate_targets(tmp_path):
    data = config_for()
    data["mappings"].append(
        {
            "id": "other",
            "sources": ["lib/**/*.py"],
            "targets": data["mappings"][0]["targets"],
        }
    )
    with pytest.raises(ConfigurationError, match="Duplicate target"):
        parse_config(data, tmp_path)


def test_rejects_recursive_target_source(tmp_path):
    data = config_for("src/generated.md")
    data["mappings"][0]["sources"] = ["src/**"]
    with pytest.raises(ConfigurationError, match="included by source"):
        parse_config(data, tmp_path)


def test_rejects_markers_on_api_target(tmp_path):
    data = config_for()
    target = data["mappings"][0]["targets"][0]
    target["kind"] = "api"
    with pytest.raises(ConfigurationError, match="must not define"):
        parse_config(data, tmp_path)


def test_rejects_unknown_root_fields(tmp_path):
    data = config_for()
    data["commands"] = ["unsafe"]
    with pytest.raises(ConfigurationError):
        parse_config(data, tmp_path)


def test_rejects_cross_mapping_generated_source_loop(tmp_path):
    data = config_for("docs/reference.md")
    data["mappings"].append(
        {
            "id": "docs-index",
            "sources": ["docs/**/*.md"],
            "targets": [
                {
                    "path": "site/index.md",
                    "kind": "api",
                    "generator": "index",
                }
            ],
        }
    )
    with pytest.raises(ConfigurationError, match="included by source"):
        parse_config(data, tmp_path)

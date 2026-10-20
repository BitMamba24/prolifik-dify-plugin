"""The plugin's YAML, checked with the Dify SDK's own models and against the
Marketplace submission rules (langgenius/dify-plugins
docs/plugin-submission-requirements.md and the dify-marketplace-toolkit
validators), so a broken listing fails here instead of in their review."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
import yaml
from dify_plugin.core.entities.plugin.setup import PluginConfiguration
from dify_plugin.entities.tool import ToolProviderConfiguration

from prolifik_api.client import API_BASE, PLUGIN_VERSION

from conftest import ROOT, tool_class

MANIFEST = yaml.safe_load((ROOT / "manifest.yaml").read_text())
PROVIDER_FILE = ROOT / MANIFEST["plugins"]["tools"][0]
PROVIDER = yaml.safe_load(PROVIDER_FILE.read_text())
TOOL_FILES = [ROOT / path for path in PROVIDER["tools"]]
TOOL_NAMES = [path.stem for path in TOOL_FILES]

# Stock AI tells and characters the house style bans from user-facing text.
BANNED_CHARS = {"—": "em dash", "–": "en dash", "“": "curly quote", "”": "curly quote", "’": "curly apostrophe"}
REPO_HOSTS = r"(?:github\.com|gitlab\.com|bitbucket\.org|gitee\.com|codeberg\.org|git\.sr\.ht)"


def test_manifest_loads_with_the_sdk() -> None:
    PluginConfiguration(**MANIFEST)


def test_manifest_has_every_field_marketplace_review_requires() -> None:
    for field in ("author", "name", "version", "type", "icon", "plugins", "privacy", "repo", "contact"):
        assert MANIFEST.get(field), f"manifest.yaml is missing {field}"
    assert MANIFEST["type"] == "plugin"
    assert MANIFEST["label"]["en_US"] and MANIFEST["description"]["en_US"]
    meta = MANIFEST["meta"]
    assert meta["version"] and meta["arch"] and meta["minimum_dify_version"]
    assert meta["runner"] == {"language": "python", "version": "3.12", "entrypoint": "main"}
    assert "dify" not in MANIFEST["author"] and "langgenius" not in MANIFEST["author"]
    assert re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]+", MANIFEST["contact"])
    assert re.fullmatch(rf"https://{REPO_HOSTS}/[^\s]+", MANIFEST["repo"])


def test_versions_agree() -> None:
    assert MANIFEST["version"] == PLUGIN_VERSION, "bump PLUGIN_VERSION in prolifik_api/client.py with manifest.yaml"


def test_icon_and_privacy_files_exist() -> None:
    assert (ROOT / "_assets" / MANIFEST["icon"]).is_file()
    assert (ROOT / "_assets" / PROVIDER["identity"]["icon"]).is_file()
    assert MANIFEST["privacy"] == "PRIVACY.md" and (ROOT / "PRIVACY.md").is_file()


def test_network_domains_cover_every_host_the_code_calls() -> None:
    declared = set(MANIFEST["network"]["domains"])
    assert API_BASE.split("/")[2] in declared
    hosts_in_code = set()
    for path in [*ROOT.glob("prolifik_api/*.py"), *ROOT.glob("tools/*.py"), *ROOT.glob("provider/*.py")]:
        for host in re.findall(r"https://([a-z0-9.-]+)", path.read_text()):
            hosts_in_code.add(host.rstrip("."))
    # Links in help text point at the app; requests only ever go to API_BASE.
    assert hosts_in_code <= declared | {"getprolifik.com"}, hosts_in_code - declared


def test_readme_links_the_source_repository_and_getprolifik() -> None:
    readme = (ROOT / "README.md").read_text()
    assert MANIFEST["repo"] in readme
    assert "https://getprolifik.com" in readme
    assert not re.search(r"[㐀-䶿一-鿿]", readme), "the primary README must be English"


def test_requirements_follow_the_dependency_policy() -> None:
    lines = [line.strip() for line in (ROOT / "requirements.txt").read_text().splitlines() if line.strip() and not line.startswith("#")]
    names = {}
    for line in lines:
        assert not re.search(r"git\+|https?://|^-e|^\.", line), f"no git, URL or local installs: {line}"
        # Exact pins: reproducible installs, and the Marketplace's OSV lookup
        # only checks exact versions.
        assert re.fullmatch(r"[A-Za-z0-9_.-]+==[0-9][0-9A-Za-z.]*", line), f"pin an exact version: {line}"
        names[line.split("==")[0].lower().replace("_", "-")] = line
    floor = names["dify-plugin"].split("==")[1]
    assert tuple(int(part) for part in floor.split(".")) >= (0, 9, 0)
    assert "requests" in names


def test_provider_and_tools_load_with_the_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)  # the SDK reads tool files relative to the plugin root
    config = ToolProviderConfiguration(**yaml.safe_load(PROVIDER_FILE.read_text()))
    assert [tool.identity.name for tool in config.tools] == TOOL_NAMES
    assert [credential.name for credential in config.credentials_schema] == ["api_key"]
    assert config.credentials_schema[0].type.value == "secret-input"


def test_every_tool_file_is_listed_in_the_provider() -> None:
    on_disk = sorted(path.stem for path in (ROOT / "tools").glob("*.yaml"))
    assert on_disk == sorted(TOOL_NAMES)
    assert sorted(path.stem for path in (ROOT / "tools").glob("*.py")) == on_disk


@pytest.mark.parametrize("name", TOOL_NAMES)
def test_tool_loads_as_exactly_one_tool_class(name: str) -> None:
    tool_class(name)


@pytest.mark.parametrize("name", TOOL_NAMES)
def test_tool_yaml_is_complete(name: str) -> None:
    spec = yaml.safe_load((ROOT / "tools" / f"{name}.yaml").read_text())
    assert spec["identity"]["name"] == name
    assert spec["identity"]["author"] == MANIFEST["author"]
    assert spec["extra"]["python"]["source"] == f"tools/{name}.py"
    assert spec["description"]["human"]["en_US"] and spec["description"]["llm"]
    for param in spec.get("parameters") or []:
        where = f"{name}.{param['name']}"
        assert param["label"]["en_US"], where
        assert param["human_description"]["en_US"], where
        assert param.get("llm_description"), where
        assert param["form"] in {"llm", "form"}, where
        if param["type"] == "select":
            assert param.get("options"), where


@pytest.mark.parametrize("name", TOOL_NAMES)
def test_output_schema_matches_the_variables_the_tool_emits(name: str) -> None:
    spec = yaml.safe_load((ROOT / "tools" / f"{name}.yaml").read_text())
    schema = spec["output_schema"]
    assert schema["type"] == "object"
    declared = list(schema["properties"])
    source = (ROOT / "tools" / f"{name}.py").read_text()
    variables = next(
        ast.literal_eval(node.value)
        for node in ast.parse(source).body
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "VARIABLES" for t in node.targets)
    )
    # Dify hands a workflow None for a declared variable the tool never emits.
    assert sorted(variables) == sorted(declared)


def user_facing_files() -> list[Path]:
    return [ROOT / "manifest.yaml", PROVIDER_FILE, *TOOL_FILES, ROOT / "README.md", ROOT / "PRIVACY.md"]


@pytest.mark.parametrize("path", user_facing_files(), ids=lambda p: p.name)
def test_user_facing_text_has_no_banned_characters(path: Path) -> None:
    text = path.read_text()
    found = {label for char, label in BANNED_CHARS.items() if char in text}
    assert not found, f"{path.name} has {', '.join(sorted(found))}"

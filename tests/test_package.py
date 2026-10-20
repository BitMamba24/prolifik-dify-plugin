"""Checks a built .difypkg: only runtime files, nothing the Marketplace
refuses. Skipped until scripts/package.sh (or `dify plugin package`) has
written one to dist/; set DIFYPKG to check a package elsewhere."""

from __future__ import annotations

import os
import re
import zipfile
from pathlib import Path

import pytest
import yaml

from conftest import ROOT

MANIFEST = yaml.safe_load((ROOT / "manifest.yaml").read_text())
EXPECTED = ROOT / "dist" / f"{MANIFEST['name']}-{MANIFEST['version']}.difypkg"
PACKAGE = Path(os.environ["DIFYPKG"]) if os.environ.get("DIFYPKG") else EXPECTED

FORBIDDEN = re.compile(
    r"(^|/)(tests/|scripts/|\.git/|\.github/|\.venv/|venv/|__pycache__/|\.pytest_cache/|\.idea/|\.vscode/)"
    r"|(^|/)(\.env(\..*)?|\.DS_Store|PUBLISHING\.md|pytest\.ini)$|\.pyc$|\.difypkg$"
)
REQUIRED = {"manifest.yaml", "main.py", "requirements.txt", "README.md", "PRIVACY.md", "_assets/icon.png", "provider/prolifik.yaml", "provider/prolifik.py"}

pytestmark = pytest.mark.skipif(not PACKAGE.is_file(), reason=f"no package at {PACKAGE}")


def names() -> list[str]:
    with zipfile.ZipFile(PACKAGE) as archive:
        return archive.namelist()


def test_package_holds_the_runtime_files() -> None:
    files = set(names())
    assert REQUIRED <= files, REQUIRED - files
    for tool in yaml.safe_load((ROOT / "provider" / "prolifik.yaml").read_text())["tools"]:
        assert tool in files and tool.replace(".yaml", ".py") in files


def test_package_holds_nothing_the_marketplace_refuses() -> None:
    bad = [name for name in names() if FORBIDDEN.search(name)]
    assert not bad, bad


def test_package_manifest_is_the_current_one() -> None:
    with zipfile.ZipFile(PACKAGE) as archive:
        packaged = yaml.safe_load(archive.read("manifest.yaml"))
    assert packaged["version"] == MANIFEST["version"], "rebuild the package after bumping the version"

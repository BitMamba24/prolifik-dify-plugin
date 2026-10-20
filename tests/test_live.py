"""Read-only calls against the real API. Skipped unless PROLIFIK_TEST_API_KEY
holds a key with content:read and clipper:read. Only GET requests: nothing
here creates a job, spends clip minutes or renders, or posts anything."""

from __future__ import annotations

import os

import pytest

from prolifik_api.client import ProlifikClient

from conftest import make_tool, run

KEY = os.environ.get("PROLIFIK_TEST_API_KEY", "").strip()

pytestmark = pytest.mark.skipif(not KEY, reason="set PROLIFIK_TEST_API_KEY to run read-only live checks")


def test_live_key_validates() -> None:
    from provider.prolifik import ProlifikProvider

    ProlifikProvider().validate_credentials({"api_key": KEY})


def test_live_list_brands() -> None:
    out = run(make_tool("list_brands", api_key=KEY), {})
    assert isinstance(out["json"]["brands"], list)


def test_live_list_videos() -> None:
    out = run(make_tool("list_videos", api_key=KEY), {"limit": 2, "status": "all"})
    assert isinstance(out["variables"]["videos"], list)


def test_live_latest_clip_job_reads() -> None:
    jobs = ProlifikClient(KEY).get("/clipper/jobs", {"limit": 1}).get("jobs") or []
    if not jobs:
        pytest.skip("the test account has no clip jobs")
    out = run(make_tool("get_clip_job", api_key=KEY), {"job_id": jobs[0]["job_id"]})
    assert out["variables"]["job_id"] == jobs[0]["job_id"]

"""What each tool sends to the API and what it hands back to Dify."""

from __future__ import annotations

import pytest
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from prolifik_api.client import ProlifikError

from conftest import API, TEST_KEY, FakeHttp, make_tool, run, tool_globals

BRAND = "5b0e8d34-7c21-4f9a-a6d2-93e1c4b7f058"
OTHER_BRAND = "7c0e8d34-7c21-4f9a-a6d2-93e1c4b7f058"
SOURCE = "c2d4e6f8-1a3b-4c5d-9e7f-0a1b2c3d4e5f"
JOB = "e1f2a3b4-c5d6-4e7f-8a9b-0c1d2e3f4a5b"

BRANDS = {
    "activeBrandId": BRAND,
    "brands": [
        {"id": OTHER_BRAND, "name": "Old Brand", "isActive": False},
        {"id": BRAND, "name": "Acme Coffee", "websiteUrl": "https://acmecoffee.com", "isActive": True},
    ],
}
JOB_RESPONSE = {
    "job": {
        "id": JOB,
        "brandId": BRAND,
        "format": "kinetic-type",
        "status": "queued",
        "requestedPieces": 2,
        "createdAt": "2026-10-20T12:00:00.000Z",
    },
    "notice": None,
}


def call(http: FakeHttp, index: int) -> tuple[str, str, dict]:
    request = http.calls[index]
    return request["method"], request["url"], request


# --- provider ---------------------------------------------------------------


def test_credentials_are_validated_with_a_read_of_usage(http: FakeHttp) -> None:
    from provider.prolifik import ProlifikProvider

    http.queue(200, {"plan": "pro"})
    ProlifikProvider().validate_credentials({"api_key": TEST_KEY})
    method, url, request = call(http, 0)
    assert (method, url) == ("GET", f"{API}/usage")
    assert request["headers"]["Authorization"] == f"Bearer {TEST_KEY}"


def test_bad_credentials_raise_the_dify_validation_error(http: FakeHttp) -> None:
    from provider.prolifik import ProlifikProvider

    http.queue(401, {"error": {"code": "invalid_api_key"}})
    with pytest.raises(ToolProviderCredentialValidationError, match="invalid, expired or revoked"):
        ProlifikProvider().validate_credentials({"api_key": TEST_KEY})


def test_empty_credentials_never_reach_the_api(http: FakeHttp) -> None:
    from provider.prolifik import ProlifikProvider

    with pytest.raises(ToolProviderCredentialValidationError, match="Add your Prolifik API key"):
        ProlifikProvider().validate_credentials({"api_key": ""})
    assert http.calls == []


# --- list_brands --------------------------------------------------------------


def test_list_brands(http: FakeHttp) -> None:
    http.queue(200, BRANDS)
    out = run(make_tool("list_brands"), {})
    assert call(http, 0)[:2] == ("GET", f"{API}/brands")
    assert out["variables"]["active_brand_id"] == BRAND
    acme = out["json"]["brands"][1]
    assert acme["name"] == "Acme Coffee" and acme["is_active_brand"] and acme["usable_on_plan"]
    assert "Old Brand" in out["text"] and "locked on current plan" in out["text"]


# --- create_videos ------------------------------------------------------------


def test_create_videos_uses_the_active_brand_when_none_is_given(http: FakeHttp) -> None:
    http.queue(200, BRANDS).queue(202, JOB_RESPONSE)
    out = run(make_tool("create_videos"), {"format": "kinetic-type", "count": 2})
    assert call(http, 0)[:2] == ("GET", f"{API}/brands")
    method, url, request = call(http, 1)
    assert (method, url) == ("POST", f"{API}/content/jobs")
    assert request["json"] == {"brandId": BRAND, "format": "kinetic-type", "count": 2}
    assert request["headers"]["Idempotency-Key"].startswith("dify:job:")
    assert out["variables"]["job_id"] == JOB
    assert out["variables"]["status"] == "queued"
    assert "Get Video Job" in out["text"]


def test_create_videos_maps_every_field(http: FakeHttp) -> None:
    http.queue(202, JOB_RESPONSE)
    run(
        make_tool("create_videos"),
        {
            "format": "carousel",
            "count": 3.0,
            "brand_id": f" {BRAND} ",
            "content_source_id": SOURCE,
            "texts": "Hook one | Slide two\n\nOnly slide\n\n",
            "include_logo": True,
            "mention_brand": "false",
        },
    )
    assert len(http.calls) == 1  # a given brand needs no brand lookup
    assert http.calls[0]["json"] == {
        "brandId": BRAND,
        "format": "carousel",
        "count": 3,
        "contentSourceId": SOURCE,
        "customTexts": [{"slides": ["Hook one", "Slide two"]}, None, {"slides": ["Only slide"]}],
        "includeLogo": True,
        "mentionBrand": False,
    }


def test_create_videos_refuses_more_texts_than_videos(http: FakeHttp) -> None:
    with pytest.raises(ProlifikError, match="line for video 2"):
        run(make_tool("create_videos"), {"format": "kinetic-type", "count": 1, "brand_id": BRAND, "texts": "a\nb"})
    assert http.calls == []


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"format": "talking-head"}, "Format must be one of"),
        ({"format": "kinetic-type", "count": 51}, "from 1 to 50"),
        ({"format": "kinetic-type", "count": 1.5}, "whole number"),
        ({"format": "kinetic-type", "source_url": "https://a.com", "content_source_id": SOURCE}, "not both"),
        ({"format": "kinetic-type", "source_url": "file:///etc/passwd"}, "must start with https://"),
    ],
)
def test_create_videos_checks_inputs_before_calling_the_api(http: FakeHttp, params: dict, message: str) -> None:
    with pytest.raises(ProlifikError, match=message):
        run(make_tool("create_videos"), {"brand_id": BRAND, **params})
    assert http.calls == []


def test_create_videos_from_a_url_adds_the_source_and_waits_until_ready(http: FakeHttp, monkeypatch: pytest.MonkeyPatch) -> None:
    module = tool_globals("create_videos")
    sleeps: list[float] = []
    monkeypatch.setitem(module, "sleep", sleeps.append)
    pending = {"source": {"id": SOURCE, "brandId": BRAND, "status": "pending"}}
    ready = {"source": {"id": SOURCE, "brandId": BRAND, "status": "ready"}}
    http.queue(202, pending).queue(200, pending).queue(200, ready).queue(202, JOB_RESPONSE)

    out = run(make_tool("create_videos"), {"format": "b-roll", "brand_id": BRAND, "source_url": "https://acmecoffee.com/blog/x"})

    assert [(c["method"], c["url"]) for c in http.calls] == [
        ("POST", f"{API}/content/sources"),
        ("GET", f"{API}/content/sources/{SOURCE}"),
        ("GET", f"{API}/content/sources/{SOURCE}"),
        ("POST", f"{API}/content/jobs"),
    ]
    assert http.calls[0]["json"] == {"brandId": BRAND, "url": "https://acmecoffee.com/blog/x"}
    assert http.calls[3]["json"]["contentSourceId"] == SOURCE
    assert sleeps == [module["SOURCE_POLL_SECONDS"], module["SOURCE_POLL_SECONDS"]]
    assert out["variables"]["job_id"] == JOB


def test_create_videos_stops_waiting_and_says_to_run_again(http: FakeHttp, monkeypatch: pytest.MonkeyPatch) -> None:
    module = tool_globals("create_videos")
    clock = iter([0.0, 30.0, 91.0])
    monkeypatch.setitem(module, "monotonic", lambda: next(clock))
    monkeypatch.setitem(module, "sleep", lambda _s: None)
    pending = {"source": {"id": SOURCE, "status": "pending"}}
    http.queue(202, pending).queue(200, pending)
    with pytest.raises(ProlifikError, match="still reading .* Run this step again with the same inputs"):
        run(make_tool("create_videos"), {"format": "b-roll", "brand_id": BRAND, "source_url": "https://a.com/p"})
    assert http.calls[-1]["method"] == "GET"  # no job was created


def test_create_videos_reports_a_failed_source(http: FakeHttp) -> None:
    http.queue(202, {"source": {"id": SOURCE, "status": "failed", "error": "403 from the site"}})
    with pytest.raises(ProlifikError, match="403 from the site"):
        run(make_tool("create_videos"), {"format": "b-roll", "brand_id": BRAND, "source_url": "https://a.com/p"})


def test_create_videos_retry_in_the_same_chat_turn_reuses_the_job_key(http: FakeHttp) -> None:
    params = {"format": "kinetic-type", "brand_id": BRAND}
    http.queue(202, JOB_RESPONSE).queue(202, JOB_RESPONSE).queue(202, JOB_RESPONSE)
    run(make_tool("create_videos", message_id="m1"), params)
    run(make_tool("create_videos", message_id="m1"), params)
    run(make_tool("create_videos", message_id="m2"), params)
    keys = [c["headers"]["Idempotency-Key"] for c in http.calls]
    assert keys[0] == keys[1]
    assert keys[2] != keys[0]


def test_create_videos_without_brands_says_to_add_one(http: FakeHttp) -> None:
    http.queue(200, {"brands": [], "activeBrandId": None})
    with pytest.raises(ProlifikError, match="no brand yet"):
        run(make_tool("create_videos"), {"format": "kinetic-type"})


# --- get_video_job ------------------------------------------------------------


def test_get_video_job(http: FakeHttp) -> None:
    http.queue(
        200,
        {
            "job": {"id": JOB, "status": "completed", "format": "kinetic-type"},
            "pieces": [
                {"id": "p1", "status": "ready", "format": "kinetic-type", "videoUrl": "https://media.example/p1.mp4", "script": {"hook": "Cold brew, ranked"}},
                {"id": "p2", "status": "failed", "format": "kinetic-type", "failureReason": "No renders left"},
            ],
        },
    )
    out = run(make_tool("get_video_job"), {"job_id": JOB})
    assert call(http, 0)[:2] == ("GET", f"{API}/content/jobs/{JOB}")
    assert out["variables"]["is_finished"] is True
    assert out["variables"]["video_urls"] == ["https://media.example/p1.mp4"]
    assert "1 of 2 videos ready" in out["text"]
    assert "No renders left" in out["text"]


def test_get_video_job_refuses_a_path_like_id(http: FakeHttp) -> None:
    with pytest.raises(ProlifikError, match="must be a Prolifik ID"):
        run(make_tool("get_video_job"), {"job_id": "../brands"})
    assert http.calls == []


# --- list_videos --------------------------------------------------------------


def test_list_videos_defaults_to_ready(http: FakeHttp) -> None:
    http.queue(200, {"pieces": [], "hasMore": False, "nextCursor": None})
    run(make_tool("list_videos"), {})
    assert call(http, 0)[:2] == ("GET", f"{API}/content/pieces")
    assert http.calls[0]["params"] == {"status": "ready", "limit": 20}


def test_list_videos_passes_filters_and_all_drops_status(http: FakeHttp) -> None:
    http.queue(200, {"pieces": [{"id": "p1", "status": "pending", "format": "b-roll"}], "hasMore": True, "nextCursor": "cur_2"})
    out = run(make_tool("list_videos"), {"brand_id": BRAND, "format": "b-roll", "status": "all", "limit": 5, "before": "cur_1"})
    assert http.calls[0]["params"] == {"brandId": BRAND, "format": "b-roll", "limit": 5, "before": "cur_1"}
    assert out["variables"]["has_more"] is True
    assert out["variables"]["next_cursor"] == "cur_2"


# --- create_clips -------------------------------------------------------------


def test_create_clips_maps_every_field(http: FakeHttp) -> None:
    http.queue(202, {"job_id": "3f9c2a7be41d", "status": "queued", "created_at": "2026-10-20T12:00:00Z"})
    out = run(
        make_tool("create_clips"),
        {
            "video_url": " https://www.youtube.com/watch?v=dQw4w9WgXcQ ",
            "clip_count": 5,
            "clip_length": "60-90",
            "video_type": "podcast",
            "language": "ES",
            "caption_style": "karaoke",
            "layout": "smart",
            "aspect_ratio": "4:5",
            "instructions": "only the product demo",
        },
    )
    method, url, request = call(http, 0)
    assert (method, url) == ("POST", f"{API}/clipper/jobs")
    assert request["json"] == {
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "numClips": 5,
        "minDuration": 60,
        "maxDuration": 90,
        "captionStyle": "karaoke",
        "layout": "smart",
        "aspectRatio": "4:5",
        "userPrompt": "only the product demo",
        "options": {"language": "es", "format": "podcast"},
    }
    assert request["headers"]["Idempotency-Key"].startswith("dify:job:")
    assert out["variables"] == {"job_id": "3f9c2a7be41d", "status": "queued", "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}


def test_create_clips_sends_only_the_url_by_default(http: FakeHttp) -> None:
    http.queue(202, {"job_id": "abc123", "status": "queued"})
    run(make_tool("create_clips"), {"video_url": "https://youtu.be/dQw4w9WgXcQ"})
    assert http.calls[0]["json"] == {"url": "https://youtu.be/dQw4w9WgXcQ"}


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({}, "Video URL is required"),
        ({"video_url": "youtube.com/watch?v=x"}, "starting with https://"),
        ({"video_url": "https://youtu.be/x", "clip_count": 21}, "from 1 to 20"),
        ({"video_url": "https://youtu.be/x", "layout": "zoom"}, "Layout must be one of"),
        ({"video_url": "https://youtu.be/x", "language": "english"}, "two-letter code"),
        ({"video_url": "https://youtu.be/x", "instructions": "x" * 2001}, "2,000 characters"),
    ],
)
def test_create_clips_checks_inputs_before_calling_the_api(http: FakeHttp, params: dict, message: str) -> None:
    with pytest.raises(ProlifikError, match=message):
        run(make_tool("create_clips"), params)
    assert http.calls == []


# --- get_clip_job -------------------------------------------------------------


def test_get_clip_job_completed(http: FakeHttp) -> None:
    http.queue(
        200,
        {
            "job_id": "3f9c2a7be41d",
            "status": "completed",
            "source": {"url": "https://youtu.be/x", "title": "Episode 12"},
            "clips": [
                {"clip_id": "c1", "title": "The pivot", "duration": 41.6, "virality_score": 82, "file_url": "https://media.example/c1.mp4", "hashtags": ["startup", "#founder"]},
                {"clip_id": "c2", "title": "Broken", "status": "failed", "file_url": ""},
            ],
        },
    )
    out = run(make_tool("get_clip_job"), {"job_id": "3f9c2a7be41d"})
    assert call(http, 0)[:2] == ("GET", f"{API}/clipper/jobs/3f9c2a7be41d")
    assert out["variables"]["clip_urls"] == ["https://media.example/c1.mp4"]
    assert out["variables"]["is_finished"] is True
    assert out["json"]["clips"][0]["hashtags"] == "#startup #founder"
    assert "The pivot (42s, virality 82)" in out["text"]


def test_get_clip_job_running(http: FakeHttp) -> None:
    http.queue(200, {"job_id": "abc", "status": "transcribing", "progress": {"current_step_name": "Transcribing", "percent": 40}, "clips": []})
    out = run(make_tool("get_clip_job"), {"job_id": "abc"})
    assert out["variables"]["is_finished"] is False
    assert "transcribing (Transcribing)" in out["text"]


def test_get_clip_job_failed_shows_the_error(http: FakeHttp) -> None:
    http.queue(200, {"job_id": "abc", "status": "failed", "error": "Video is private", "clips": []})
    out = run(make_tool("get_clip_job"), {"job_id": "abc"})
    assert out["variables"]["error"] == "Video is private"
    assert "failed. Video is private" in out["text"]

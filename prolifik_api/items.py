"""Flat snake_case shapes for what the tools return, matching the Zapier
integration's items (integrations/zapier/lib/items.js) so a field means the
same thing in both. Every builder emits the same keys each time, None when
the API has no value."""

from __future__ import annotations

from typing import Any

# Mirrors src/lib/content/formats.ts. talking-head (Video Hook & Demo) needs
# an uploaded demo recording, which this plugin does not handle.
FORMAT_LABELS = {
    "carousel": "Image Carousel",
    "kinetic-type": "Text Story",
    "scene-swap": "Meme Reaction",
    "b-roll": "Clip Montage",
    "caption-card": "Caption Meme",
    "talking-head": "Video Hook & Demo",
}
CREATABLE_FORMATS = ("carousel", "kinetic-type", "scene-swap", "b-roll", "caption-card")


def _str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _num(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, (int, float)) else None


def _strings(value: Any) -> list[str]:
    return [entry for entry in value if isinstance(entry, str) and entry] if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def hashtag_text(tags: Any) -> str:
    out = []
    for tag in _strings(tags):
        tag = tag.strip()
        if tag:
            out.append(tag if tag.startswith("#") else f"#{tag}")
    return " ".join(out)


def brand_item(brand: dict[str, Any], active_brand_id: str | None = None) -> dict[str, Any]:
    return {
        "id": _str(brand.get("id")),
        "name": _str(brand.get("name")) or "",
        "website_url": _str(brand.get("websiteUrl")),
        "description": _str(brand.get("description")),
        "is_active_brand": bool(active_brand_id) and brand.get("id") == active_brand_id,
        "usable_on_plan": brand.get("isActive") is True,
        "created_at": _str(brand.get("createdAt")),
    }


def video_item(piece: dict[str, Any]) -> dict[str, Any]:
    script = _dict(piece.get("script"))
    fmt = _str(piece.get("format")) or ""
    return {
        "id": _str(piece.get("id")),
        "job_id": _str(piece.get("jobId")),
        "format": fmt,
        "format_label": FORMAT_LABELS.get(fmt, fmt),
        "status": _str(piece.get("status")),
        "failure_reason": _str(piece.get("failureReason")),
        "video_url": _str(piece.get("videoUrl")),
        "thumbnail_url": _str(piece.get("thumbnailUrl")),
        "slide_urls": _strings(piece.get("slideUrls")),
        "hook": _str(script.get("hook")) or "",
        "body": _str(script.get("body")) or "",
        "cta": _str(script.get("cta")) or "",
        "slide_texts": _strings(script.get("slides")),
        "created_at": _str(piece.get("createdAt")),
        "expires_at": _str(piece.get("expiresAt")),
    }


def video_job_item(job: dict[str, Any], notice: Any = None) -> dict[str, Any]:
    fmt = _str(job.get("format")) or ""
    return {
        "job_id": _str(job.get("id")),
        "brand_id": _str(job.get("brandId")),
        "content_source_id": _str(job.get("contentSourceId")),
        "format": fmt,
        "format_label": FORMAT_LABELS.get(fmt, fmt),
        "status": _str(job.get("status")),
        "requested_videos": _num(job.get("requestedPieces")),
        "expected_videos": _num(job.get("expectedPieces")),
        "generated_videos": _num(job.get("generatedPieces")),
        "failed_videos": _num(job.get("failedPieces")),
        "created_at": _str(job.get("createdAt")),
        "completed_at": _str(job.get("completedAt")),
        "notice": _str(notice),
    }


def source_item(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _str(source.get("id")),
        "brand_id": _str(source.get("brandId")),
        "url": _str(source.get("url")),
        "title": _str(source.get("title")),
        "status": _str(source.get("status")),
        "error": _str(source.get("error")),
    }


def clip_item(clip: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _str(clip.get("clip_id")),
        "title": _str(clip.get("title")) or "",
        "hook": _str(clip.get("hook")) or "",
        "description": _str(clip.get("description")) or "",
        "hashtags": hashtag_text(clip.get("hashtags")),
        "duration": _num(clip.get("duration")) or 0,
        "start_time": _num(clip.get("start_time")) or 0,
        "end_time": _num(clip.get("end_time")) or 0,
        "virality_score": _num(clip.get("virality_score")) or 0,
        "status": _str(clip.get("status")),
        "video_url": _str(clip.get("file_url")),
        "thumbnail_url": _str(clip.get("thumbnail_url")),
    }


def clip_job_item(job: dict[str, Any]) -> dict[str, Any]:
    source = _dict(job.get("source"))
    progress = _dict(job.get("progress"))
    clips = [clip_item(clip) for clip in job.get("clips") or [] if isinstance(clip, dict)]
    return {
        "job_id": _str(job.get("job_id")),
        "status": _str(job.get("status")),
        "progress_step": _str(progress.get("current_step_name")),
        "progress_percent": _num(progress.get("percent")),
        "error": _str(job.get("error")),
        "source_url": _str(source.get("url")),
        "source_title": _str(source.get("title")),
        "source_channel": _str(source.get("channel")),
        "aspect_ratio": _str(job.get("aspect_ratio")),
        "created_at": _str(job.get("created_at")),
        "completed_at": _str(job.get("completed_at")),
        "clip_count": len(clips),
        "clips": clips,
    }

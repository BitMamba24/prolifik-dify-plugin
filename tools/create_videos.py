import time
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from prolifik_api.client import ProlifikClient, ProlifikError, is_blank, path_id
from prolifik_api.items import CREATABLE_FORMATS, FORMAT_LABELS, source_item, video_job_item
from prolifik_api.tooling import choice, client_for, emit, resolve_brand_id, to_bool, to_int, trimmed

VARIABLES = ("job_id", "status", "brand_id", "content_source_id", "requested_videos", "notice")

# A new page takes about a minute to analyse. main.py sets the plugin's request
# timeout to 180 seconds, which leaves room for this wait.
SOURCE_WAIT_SECONDS = 90
SOURCE_POLL_SECONDS = 5

# Indirection so tests can run the wait without sleeping.
sleep = time.sleep
monotonic = time.monotonic


def custom_texts(value: Any, fmt: str, count: int) -> list[dict[str, Any] | None] | None:
    """Your own text in video order. The API reads entry N as video N's text
    and a None entry lets the AI write that video, so an empty line becomes
    None to keep the lines after it on their own videos; trailing empty lines
    are dropped. Carousel lines list slides separated by "|"."""
    if is_blank(value):
        return None
    entries: list[dict[str, Any] | None] = []
    for line in str(value).replace("\r\n", "\n").split("\n"):
        if fmt == "carousel":
            slides = [slide.strip() for slide in line.split("|") if slide.strip()]
            entries.append({"slides": slides} if slides else None)
        else:
            text = line.strip()
            entries.append({"text": text} if text else None)
    while entries and entries[-1] is None:
        entries.pop()
    if not entries:
        return None
    if len(entries) > count:
        raise ProlifikError(
            f"Your Own Text has a line for video {len(entries)}, but Number of Videos is {count}. "
            "Raise Number of Videos or remove some lines."
        )
    return entries


def wait_for_source(client: ProlifikClient, source: dict[str, Any], url: str) -> dict[str, Any]:
    """Poll a content source until it is ready; fail on failed or timeout."""
    source_id = path_id(source.get("id"), "Content source ID")
    deadline = monotonic() + SOURCE_WAIT_SECONDS
    while True:
        status = source.get("status")
        if status == "ready":
            return source
        if status == "failed":
            reason = source.get("error") or "it could not be read"
            raise ProlifikError(
                f"Prolifik could not use {url} as a source: {reason}. Check that the page is public, or leave "
                "Source Page URL empty to write from the brand."
            )
        if monotonic() >= deadline:
            raise ProlifikError(
                f"Prolifik is still reading {url} (content source {source.get('id')}). Run this step again "
                "with the same inputs in a minute: it picks up the same page instead of adding it twice."
            )
        sleep(SOURCE_POLL_SECONDS)
        source = (client.get(f"/content/sources/{source_id}").get("source")) or {}


class CreateVideosTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        fmt = choice(tool_parameters.get("format"), CREATABLE_FORMATS, "Format")
        if fmt is None:
            raise ProlifikError(f"Format is required: one of {', '.join(CREATABLE_FORMATS)}.")
        count = to_int(tool_parameters.get("count"), "Number of Videos", minimum=1, maximum=50) or 1
        source_url = trimmed(tool_parameters.get("source_url"))
        source_id = trimmed(tool_parameters.get("content_source_id"))
        if source_url and source_id:
            raise ProlifikError("Give Source Page URL or Content Source ID, not both.")
        if source_url and not source_url.lower().startswith(("https://", "http://")):
            raise ProlifikError(f"Source Page URL must start with https://, got {source_url[:80]!r}.")
        texts = custom_texts(tool_parameters.get("texts"), fmt, count)

        client = client_for(self)
        brand_id = resolve_brand_id(client, tool_parameters.get("brand_id"))

        if source_url:
            created = client.post(
                "/content/sources",
                {"brandId": brand_id, "url": source_url},
                dedupe="job",
            )
            source = wait_for_source(client, created.get("source") or {}, source_url)
            source_id = source_item(source)["id"]

        data = client.post(
            "/content/jobs",
            {
                "brandId": brand_id,
                "format": fmt,
                "count": count,
                "contentSourceId": source_id,
                "customTexts": texts,
                "includeLogo": to_bool(tool_parameters.get("include_logo")),
                "mentionBrand": to_bool(tool_parameters.get("mention_brand")),
            },
            dedupe="job",
        )
        result = video_job_item(data.get("job") or {}, data.get("notice"))
        label = FORMAT_LABELS.get(fmt, fmt)
        text = (
            f"Queued {count} {label} video{'s' if count != 1 else ''}. Job ID: {result['job_id']}. "
            "Rendering takes a few minutes; call Get Video Job with this job ID for the video links."
        )
        if result["notice"]:
            text += f" Note from Prolifik: {result['notice']}"
        yield from emit(self, result, text, VARIABLES)

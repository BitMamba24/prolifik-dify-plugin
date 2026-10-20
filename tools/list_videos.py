from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from prolifik_api.items import FORMAT_LABELS, video_item
from prolifik_api.tooling import choice, client_for, emit, to_int, trimmed

VARIABLES = ("videos", "has_more", "next_cursor")
STATUSES = ("ready", "failed", "pending", "all")


def list_params(tool_parameters: dict[str, Any]) -> dict[str, Any]:
    status = choice(tool_parameters.get("status"), STATUSES, "Status") or "ready"
    return {
        "brandId": trimmed(tool_parameters.get("brand_id")),
        "format": choice(tool_parameters.get("format"), FORMAT_LABELS.keys(), "Format"),
        "status": None if status == "all" else status,
        "limit": to_int(tool_parameters.get("limit"), "Limit", minimum=1, maximum=100) or 20,
        "before": trimmed(tool_parameters.get("before")),
    }


class ListVideosTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        data = client_for(self).get("/content/pieces", list_params(tool_parameters))
        videos = [video_item(piece) for piece in data.get("pieces") or [] if isinstance(piece, dict)]
        next_cursor = data.get("nextCursor") if isinstance(data.get("nextCursor"), str) else None
        result = {"videos": videos, "has_more": data.get("hasMore") is True, "next_cursor": next_cursor}

        lines = [f"{len(videos)} video{'s' if len(videos) != 1 else ''}."]
        for video in videos:
            link = video["video_url"] or ", ".join(video["slide_urls"]) or video["status"] or ""
            caption = video["hook"] or (video["slide_texts"][0] if video["slide_texts"] else "")
            lines.append(f"- {video['format_label']} ({video['created_at'] or ''}): {caption[:80]} {link}".rstrip())
        if result["has_more"]:
            lines.append(f"More videos exist; pass {next_cursor} as Page Cursor for the next page.")
        yield from emit(self, result, "\n".join(lines), VARIABLES)

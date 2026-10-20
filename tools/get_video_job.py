from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from prolifik_api.client import path_id
from prolifik_api.items import video_item, video_job_item
from prolifik_api.tooling import client_for, emit

VARIABLES = ("job_id", "status", "is_finished", "video_urls", "videos")
FINISHED = frozenset({"ready_for_review", "completed", "partially_failed", "canceled", "failed"})


class GetVideoJobTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        job_id = path_id(tool_parameters.get("job_id"), "Video Job ID")
        data = client_for(self).get(f"/content/jobs/{job_id}")
        job = video_job_item(data.get("job") or {})
        videos = [video_item(piece) for piece in data.get("pieces") or [] if isinstance(piece, dict)]
        ready = [video for video in videos if video["status"] == "ready"]
        result = {
            **job,
            "is_finished": job["status"] in FINISHED,
            "video_urls": [video["video_url"] for video in ready if video["video_url"]],
            "videos": videos,
        }

        lines = [f"Video job {job['job_id']} is {job['status']}: {len(ready)} of {len(videos)} videos ready."]
        for video in ready:
            link = video["video_url"] or ", ".join(video["slide_urls"]) or "no link yet"
            caption = video["hook"] or (video["slide_texts"][0] if video["slide_texts"] else "")
            lines.append(f"- {video['format_label']}: {caption[:80]} {link}".rstrip())
        failed = [video for video in videos if video["status"] == "failed"]
        for video in failed:
            lines.append(f"- Failed: {video['failure_reason'] or 'no reason given'} (video {video['id']})")
        if not result["is_finished"]:
            lines.append("Still running; check again in about a minute.")
        yield from emit(self, result, "\n".join(lines), VARIABLES)

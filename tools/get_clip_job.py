from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from prolifik_api.client import path_id
from prolifik_api.items import clip_job_item
from prolifik_api.tooling import client_for, emit

VARIABLES = ("job_id", "status", "is_finished", "clip_urls", "clips", "error")
FINISHED = frozenset({"completed", "failed", "cancelled"})


class GetClipJobTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        job_id = path_id(tool_parameters.get("job_id"), "Clip Job ID")
        job = clip_job_item(client_for(self).get(f"/clipper/jobs/{job_id}"))
        clips = [clip for clip in job["clips"] if clip["video_url"] and clip["status"] != "failed"]
        result = {
            **job,
            "is_finished": job["status"] in FINISHED,
            "clip_urls": [clip["video_url"] for clip in clips],
        }

        if job["status"] == "completed":
            lines = [f"Clip job {job['job_id']} is completed with {len(clips)} clips:"]
            for clip in clips:
                lines.append(
                    f"- {clip['title'] or clip['hook'] or 'Untitled'} ({round(clip['duration'])}s, "
                    f"virality {clip['virality_score']}): {clip['video_url']}"
                )
        elif job["status"] in FINISHED:
            lines = [f"Clip job {job['job_id']} is {job['status']}." + (f" {job['error']}" if job["error"] else "")]
        else:
            step = f" ({job['progress_step']})" if job["progress_step"] else ""
            lines = [f"Clip job {job['job_id']} is {job['status']}{step}. Check again in a minute or two."]
        yield from emit(self, result, "\n".join(lines), VARIABLES)

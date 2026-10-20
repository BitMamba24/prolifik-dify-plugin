import re
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from prolifik_api.client import ProlifikError
from prolifik_api.tooling import choice, client_for, emit, to_int, trimmed

VARIABLES = ("job_id", "status", "video_url")

# Length presets from the in-app clip form, as in the Zapier action.
CLIP_LENGTHS = {
    "10-30": (10, 30),
    "30-60": (30, 60),
    "60-90": (60, 90),
    "90-180": (90, 180),
    "180-300": (180, 300),
}
VIDEO_TYPES = ("generic", "podcast", "reaction", "casino", "broadcast")
CAPTION_STYLES = ("classic", "karaoke", "bold", "minimal", "neon", "none")
LAYOUTS = ("blur", "crop", "smart")
ASPECT_RATIOS = ("9:16", "1:1", "4:5", "16:9")
LANGUAGE = re.compile(r"^(auto|[a-z]{2,3})$")


def clip_job_body(tool_parameters: dict[str, Any]) -> dict[str, Any]:
    video_url = trimmed(tool_parameters.get("video_url"))
    if not video_url:
        raise ProlifikError("Video URL is required: a link to one YouTube, Twitch or Kick video.")
    if not video_url.lower().startswith(("https://", "http://")):
        raise ProlifikError(f"Video URL must be a link starting with https://, got {video_url[:80]!r}.")
    length = CLIP_LENGTHS.get(choice(tool_parameters.get("clip_length"), CLIP_LENGTHS, "Clip Length") or "", (None, None))
    language = trimmed(tool_parameters.get("language"))
    if language is not None:
        language = language.lower()
        if not LANGUAGE.match(language):
            raise ProlifikError(f"Spoken Language must be a two-letter code such as en or es, got {language[:20]!r}.")
    instructions = trimmed(tool_parameters.get("instructions"))
    if instructions and len(instructions) > 2000:
        raise ProlifikError(f"Instructions can be up to 2,000 characters, got {len(instructions)}.")
    return {
        "url": video_url,
        "numClips": to_int(tool_parameters.get("clip_count"), "Number of Clips", minimum=1, maximum=20),
        "minDuration": length[0],
        "maxDuration": length[1],
        "captionStyle": choice(tool_parameters.get("caption_style"), CAPTION_STYLES, "Caption Style"),
        "layout": choice(tool_parameters.get("layout"), LAYOUTS, "Layout"),
        "aspectRatio": choice(tool_parameters.get("aspect_ratio"), ASPECT_RATIOS, "Aspect Ratio"),
        "userPrompt": instructions,
        "options": {
            "language": language,
            "format": choice(tool_parameters.get("video_type"), VIDEO_TYPES, "Video Type"),
        },
    }


class CreateClipsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        body = clip_job_body(tool_parameters)
        job = client_for(self).post("/clipper/jobs", body, dedupe="job")
        result = {
            "job_id": job.get("job_id"),
            "status": job.get("status") or "queued",
            "video_url": body["url"],
            "created_at": job.get("created_at"),
        }
        text = (
            f"Clip job {result['job_id']} is {result['status']}. Clipping takes several minutes depending on the "
            "video's length; call Get Clip Job with this job ID for the clips."
        )
        yield from emit(self, result, text, VARIABLES)

# Prolifik for Dify

[Prolifik](https://getprolifik.com) makes short-form social video. This plugin gives Dify agents and workflows two of its jobs: cutting a long YouTube, Twitch or Kick video into captioned vertical clips, and making a batch of branded videos (Text Story, Caption Meme, Meme Reaction, Clip Montage, Image Carousel) for one of your brands.

- Author: Prolifik
- Contact: info@getprolifik.com
- Source repository: https://github.com/BitMamba24/prolifik-dify-plugin
- API reference: https://getprolifik.com/docs/api

## Tools

| Tool | What it does | API call |
|---|---|---|
| List Brands | Lists your brands with their IDs and marks the active one. | `GET /brands` |
| Create Videos | Queues branded videos, written from your brand, a web page you give it, or your own text. | `POST /content/sources` (only with a page URL), `POST /content/jobs` |
| Get Video Job | Shows a video job's status and the videos it has made, with download links. | `GET /content/jobs/{id}` |
| List Videos | Lists your videos, newest first, filtered by brand, format and status. | `GET /content/pieces` |
| Create Clips | Queues an AI Clipper job for one YouTube, Twitch or Kick video. | `POST /clipper/jobs` |
| Get Clip Job | Shows a clip job's progress and, once done, its clips with download links. | `GET /clipper/jobs/{id}` |

Every tool returns a one-paragraph summary for agents, the full result as JSON, and named output variables (such as `job_id`, `status`, `video_urls`, `clip_urls`) for workflow nodes.

Nothing in this plugin posts to social media. Publishing stays in the Prolifik app, where you pick the accounts and review the caption.

## Setup

1. You need a Prolifik account on a paid plan (Lite, Starter, Pro or Enterprise). API keys are not available on the free trial.
2. In Prolifik, open Settings > Developer API (https://app.getprolifik.com/home?settings=developer) and create a key. Tick these scopes: `content:read`, `content:write`, `clipper:read`, `clipper:write`. Pick how long it lasts (30, 90 or 365 days). The key starts with `plk_live_` and is shown once.
3. In Dify, install Prolifik from the Marketplace, open the plugin, set up its authorization and paste the key into API Key. Dify checks the key with a read of your plan usage before saving it.

When the key expires or is revoked, every tool fails with a message saying so. Create a new key and update the credentials in the same place.

## Usage

### In an agent or chatflow

Add the tools to an agent and ask in plain words:

- "Clip https://www.youtube.com/watch?v=... into 5 podcast clips under a minute, karaoke captions." The agent calls Create Clips, then Get Clip Job until the clips are ready.
- "Make 3 Text Story videos for Acme Coffee from https://acmecoffee.com/blog/cold-brew-ratios." The agent finds the brand with List Brands, calls Create Videos with the page, then Get Video Job.
- "Show my last 10 ready videos." List Videos.

Both job types run in the background. Create Clips and Create Videos return a `job_id` straight away; clips take several minutes depending on the video's length, videos a few minutes. A good agent instruction is "after creating a job, check it every minute until it is finished".

### In a workflow

A typical clip workflow:

1. Create Clips with the video URL from the start node.
2. A loop node that runs Get Clip Job with `{{job_id}}`, waits 60 seconds between runs, and stops when `is_finished` is true.
3. Use `clip_urls` or `clips` in the next node (a spreadsheet row, a message, a review step).

The same pattern works for Create Videos and Get Video Job (`video_urls`, `videos`).

### Create Videos inputs

- **Format**: Text Story, Caption Meme, Meme Reaction, Clip Montage or Image Carousel. Video Hook & Demo needs a recording uploaded in Prolifik, so it is left out here.
- **Brand ID**: leave empty to use the brand active in your account.
- **Source Page URL**: a public page to write the videos from. Prolifik reads it first, which takes about a minute; the tool waits up to 90 seconds. If the page is still being read after that, the tool fails with a message to run it again with the same inputs, and the second run picks up the same page.
- **Your Own Text**: one line per video, used word for word. An empty line lets the AI write that video. For Image Carousel, separate the slides on a line with `|`.
- **Add Brand Logo** and **Mention the Brand**: form settings, not chosen by the agent.

### Retries do not create duplicate jobs

Every create sends an Idempotency-Key, and Prolifik keeps each key's result for 24 hours. The key comes from the request itself, the Dify app, the chat message (when there is one) and the UTC hour. So a node retry or an agent repeating a call within the same chat turn gets the first job back instead of a second one, while asking again in a new message makes a new batch. In a workflow with no chat, two runs with identical inputs in the same hour share one job, the same rule Prolifik's Zapier integration uses.

## Limits and costs

- Clipping uses clip minutes from your plan: Lite 60, Starter 360, Pro 1,400 per month, counted on the source video's length. A job that fails gives its minutes back.
- Each video uses one render from your monthly render budget (Lite 1,000, Starter 2,000, Pro 4,000). A job asking for more renders than you have left is refused before anything is made.
- Each API key may make 120 requests a minute, and clip jobs have a lower hourly cap. A tool that hits a limit fails with the wait time from Prolifik.
- Download links expire: video links after about an hour, clip links after 7 days. Run Get Video Job or Get Clip Job again for fresh links rather than storing old ones.

## Connection requirements

The plugin makes HTTPS requests to one host, `app.getprolifik.com` on port 443, and nowhere else. On a self-hosted Dify, the plugin daemon needs outbound internet access to that host; set a proxy in the daemon's environment if your network requires one. No inbound connection, webhook or callback URL is needed.

The API key is sent only in the Authorization header to that host. Redirects are not followed, and tool inputs that end up in a URL path (job IDs) are checked to be plain IDs first.

## Privacy

See [PRIVACY.md](PRIVACY.md). Prolifik's own privacy policy is at https://getprolifik.com/privacy.

## Support

Email info@getprolifik.com with the tool name, the time of the run and any Request ID from the error message. Never send your API key.

## Changelog

- 0.1.0: first release with List Brands, Create Videos, Get Video Job, List Videos, Create Clips and Get Clip Job.

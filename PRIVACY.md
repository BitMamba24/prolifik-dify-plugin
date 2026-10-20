# Privacy Policy: Prolifik plugin for Dify

Last updated: 20 October 2026

This plugin is published by Prolifik (https://getprolifik.com) and connects Dify to the Prolifik public API at `app.getprolifik.com`. This page covers what the plugin itself does with data. What Prolifik does with data once it reaches your account is covered by Prolifik's privacy policy at https://getprolifik.com/privacy.

## What the plugin sends, and where

The plugin sends data to one destination only: the Prolifik API at `https://app.getprolifik.com/api/v1`, over HTTPS. It sends:

- **Your Prolifik API key**, in the Authorization header of each request. Dify stores the key with its encrypted tool credentials; the plugin reads it from Dify at run time and does not keep a copy.
- **The tool inputs you or your agent provide**: video links to clip, web page links to write from, your own text for videos, brand and job IDs, and settings such as clip length or caption style.
- **An Idempotency-Key header**: a SHA-256 hash of the request, the Dify app ID, the chat message ID when there is one and the current UTC hour. The IDs are hashed, not sent in readable form. It lets Prolifik recognise a retried request so a retry does not create a second job.
- **A User-Agent header** naming the plugin and its version.

The plugin does not send data to any other third party, and it does not post anything to social media.

## What comes back

Prolifik returns your brand names and IDs, job status, generated video text, and links to the finished videos and clips. The plugin passes these to your Dify app as the tool result. Dify may keep them in its run logs and conversation history according to your Dify settings.

## What the plugin stores and logs

The plugin does not store, cache or log any user data, API keys, tool inputs or results. It has no database and writes no files. It does not use Dify's plugin storage.

## What Prolifik does with the data

Requests made through this plugin are handled the same way as requests from the Prolifik app: video and page links are fetched and processed to make your clips and videos, results are saved to your Prolifik account, and usage counts against your plan. Prolifik uses AI and hosting providers to do this work. See https://getprolifik.com/privacy for the full list of what Prolifik collects, how long it keeps it, and how to delete it.

## Your controls

- Revoke the API key at any time in Prolifik under Settings > Developer API. The plugin stops working at once.
- Remove the credentials or uninstall the plugin in Dify.
- Delete clips, videos and brands in the Prolifik app, or ask for account deletion at info@getprolifik.com.

## Contact

Questions about this policy: info@getprolifik.com.

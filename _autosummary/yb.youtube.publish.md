# yb.youtube.publish

High-level YouTube publishing: prepare → upload → captions → thumbnail.

Two entry points:

> - [`publish_content()`](#yb.youtube.publish.publish_content) — given a prepared
>   [`yb.content.PublicationContent`](yb.content.md#yb.content.PublicationContent), upload it with captions,
>   > thumbnail, and chapters (in the description).
> - [`prepare_and_publish()`](#yb.youtube.publish.prepare_and_publish) — the one-call path: transcribe/derive
>   metadata/detect chapters (via [`yb.content.prepare_content()`](yb.content.md#yb.content.prepare_content)) and
>   upload, all from a media path.

### Functions

| [`prepare_and_publish`](#yb.youtube.publish.prepare_and_publish)(media, \*[, language, ...])   | One call: prepare publication content from `media` and upload it.   |
|----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------|
| [`publish_content`](#yb.youtube.publish.publish_content)(content, \*[, ...])               | Upload a prepared `PublicationContent` to YouTube.                  |
| [`publish_video`](#yb.youtube.publish.publish_video)(video_path, metadata, \*[, ...])    | Lower-level upload: explicit `VideoMetadata` + caption tracks.      |

### Exceptions

| [`PartialPublish`](#yb.youtube.publish.PartialPublish)(result, \*, step, error)   | The video was uploaded, then a later step failed (yb#21).   |
|--------------------------------------------------------------------------------------------|-------------------------------------------------------------|

### *exception* yb.youtube.publish.PartialPublish(result, , step, error)

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

The video was uploaded, then a later step failed (yb#21).

The upload is the expensive step (1,600 quota units); captions, thumbnail
and playlist can each fail afterwards on quota, auth or a transient error.
Raising the bare error lost the new video’s id, and a re-run uploaded a
second copy. This carries what was done instead:

- `result`: the dict the publish call would have returned, as far as it
  got (`video_id`, `url`, `captions` attached so far, `thumbnail`,
  `playlist`). Persist it.
- `step`: the step that failed, e.g. `"caption ja"`.
- `__cause__`: the original error.

Finish later without re-uploading: pass `resume=err.result` to the same
call ([`publish_video()`](#yb.youtube.publish.publish_video) or [`publish_content()`](#yb.youtube.publish.publish_content); for
[`prepare_and_publish()`](#yb.youtube.publish.prepare_and_publish), call [`publish_content()`](#yb.youtube.publish.publish_content) with the content
it prepared, rather than preparing it again). Steps already done are
skipped. A resume trusts the saved result: it does not upload, so new
metadata, video path or privacy in the resuming call are ignored, and the
remaining steps target the saved `video_id`.

`result` is plain JSON-able data, and the exception pickles (so a worker
process can hand it back); `__cause__` does not survive pickling.

### yb.youtube.publish.prepare_and_publish(media, \*, language='English', language_code=None, audio_language_code=None, brand=None, extra_context=None, with_chapters=True, with_thumbnail=True, privacy_status=None, playlist=<object object>, category_id='28', config=None, client_secrets_file=None, token_file=None, progress=True, \*\*cred_kwargs)

One call: prepare publication content from `media` and upload it.

Transcribes (persisting the SRT next to the media) if needed, writes
LLM metadata, detects chapters, renders a thumbnail, then uploads with
captions + thumbnail + chapters and adds the video to the configured
playlist. `privacy_status` and `playlist` default to your `yb` config
(see [`publish_content()`](#yb.youtube.publish.publish_content)).

`cred_kwargs` reach [`get_credentials()`](yb.youtube.auth.md#yb.youtube.auth.get_credentials) (e.g.
`open_browser=False, port=8080` for headless consent).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### yb.youtube.publish.publish_content(content, \*, privacy_status=None, playlist=<object object>, category_id='28', with_chapters=True, attach_caption=True, set_thumb=True, config=None, client_secrets_file=None, token_file=None, progress=True, service=None, resume=None, \*\*cred_kwargs)

Upload a prepared `PublicationContent` to YouTube.

Maps the content to a YouTube snippet (chapters embedded in the
description when present), uploads, attaches the SRT caption track
(language = `content.audio_language` or `content.language`) and the
thumbnail when available, and adds the video to the configured playlist.

`privacy_status` and `playlist` default to your `yb` config (see
[`yb.config`](yb.config.md#module-yb.config)): unset means “use the config value”, so privacy falls back
to `unlisted` and the video joins your configured playlist. Pass
`playlist=None` to skip the playlist for one call, or `playlist="Name"`
to override the target.

`cred_kwargs` reach [`get_credentials()`](yb.youtube.auth.md#yb.youtube.auth.get_credentials) (e.g.
`open_browser=False, port=8080` for headless consent).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)
* **Returns:**
  `{"video_id", "url", "studio_url", "privacy_status", "captions",
  "thumbnail", "playlist"}`. `privacy_status` reflects what YouTube
  actually set (an unaudited project may force `"private"`); `playlist`
  is the [`add_video_to_playlist()`](yb.youtube.playlists.md#yb.youtube.playlists.add_video_to_playlist) result or
  `None`.
* **Raises:**
  [**PartialPublish**](#yb.youtube.publish.PartialPublish) – the upload succeeded and a later step failed;
      `err.result` holds the video id and what was done. Pass
      `resume=err.result` to finish without uploading again (yb#21).

### yb.youtube.publish.publish_video(video_path, metadata, \*, privacy_status=None, playlist=<object object>, captions=None, thumbnail=None, config=None, client_secrets_file=None, token_file=None, progress=True, service=None, resume=None, \*\*cred_kwargs)

Lower-level upload: explicit `VideoMetadata` + caption tracks.

`privacy_status` and `playlist` default to your `yb` config (see
[`publish_content()`](#yb.youtube.publish.publish_content)).

If a step after the upload fails, [`PartialPublish`](#yb.youtube.publish.PartialPublish) is raised with
the new video’s id and what was done so far (`err.result`). Pass
`resume=err.result` to finish without uploading again (yb#21).

`cred_kwargs` reach [`get_credentials()`](yb.youtube.auth.md#yb.youtube.auth.get_credentials) (e.g.
`open_browser=False, port=8080` for headless consent).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

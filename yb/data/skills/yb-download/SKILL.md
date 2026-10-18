---
name: yb-download
description: >
  Download a YouTube video, or just its audio, with the `yb` package — including
  metadata-only lookups, playlists, sidecars (subtitles/thumbnail/description),
  and converting the downloaded audio to a specific format (mp3, wav, ...). Use
  when the user wants to get/fetch/grab/rip a video or its audio from a YouTube
  link, extract audio from a video URL, pull a video's metadata without
  downloading, or convert an audio file's format.
---

# yb-download

Fetch media (and metadata) from YouTube via yt-dlp. Requires
`yb[download]`; converting audio formats also needs `ffmpeg` on PATH.

Destination defaults to `$YB_DOWNLOAD_DIR`, else `~/Downloads`, named
`Title (video_id).ext`.

Bot-blocked (headless server)? Give yb a Netscape-format cookies file:
`$YB_COOKIES_FILE`, else `~/.config/yb/youtube-cookies.txt`, or per call
`cookies_file=`. `cookies_from_browser=` / `extra_opts` cookie options win.
Never commit the file.

## Get a video's audio

```python
from yb.download import download_youtube_audio

r = download_youtube_audio(url)  # source format (usually .webm/Opus)
r = download_youtube_audio(url, audio_format="mp3")  # converted (needs ffmpeg)
print(r.path, r.video_id)
```

**`audio_format=None` (the default) means no conversion** — you get the bytes
exactly as YouTube served them, which needs no ffmpeg and avoids re-encoding a
lossy stream into another lossy format. Pass `audio_format` only when something
downstream needs a specific container; it's a no-op when the download already is
that format, so passing it unconditionally is safe.

- `bitrate="320k"` — for lossy targets; ignored for wav/flac/aiff/alac.
- `keep_original=True` — keep the pre-conversion download too.
- `on_error="warn"` — warn and return the unconverted file instead of raising.
  Either way **a failed conversion never costs you the download**.

## Get the video

```python
from yb.download import download_youtube_video, youtube_video_info

youtube_video_info(url)  # metadata only — title/duration/chapters, no download
download_youtube_video(url)  # best video+audio, merged to mp4
download_youtube_video(
    url,
    download_dir="~/clips",
    write_info_json=True,
    write_subtitles=True,
    subtitle_langs=("en", "fr"),
)
```

Sidecars (`write_info_json`, `write_thumbnail`, `write_description`,
`write_subtitles`, `write_auto_subtitles`) land next to the media and are
reported in `result.sidecars`. Playlists: `youtube_playlist_info` /
`download_youtube_playlist`. Any raw yt-dlp option passes through `extra_opts=`.

Long playlists, politely (audio only, resumable, one folder per item):

```python
download_youtube_playlist(
    url, fmt="bestaudio/best", merge_to=None,  # source stream, no re-encode
    pace="polite",                  # sleep 20-60 s, 1 s between requests, 4 MB/s
    download_archive="archive.txt", # re-run skips finished ids
    playlist_items="1-42",          # also title_reject="PV"
    item_folders=True,              # 001_<id>/<id>.m4a + sidecars
    embed_metadata=True,
)
```

`pace=` also exists on the video/audio downloaders (default `None` = no change).
HTTP 429 or a "confirm you're not a bot" wall raises `RateLimitedError` with a
backoff hint: wait hours, then retry paced, with the archive, cookies, and fewer
items per run.

## Convert audio you already have

```python
from yb.audio_convert import convert_audio

convert_audio("talk.webm", "mp3", bitrate="320k")  # -> talk.mp3
convert_audio("talk.webm", "wav")  # lossless: no bitrate applied
```

Returns the source unchanged if it's already in the target format. Raises
`AudioConversionError` if ffmpeg is missing or fails — always leaving the source
file untouched.

## Notes

- **YouTube downloads need Deno and yt-dlp's solver scripts.** Without them
  yt-dlp fails with `No video formats found!`. `yb[download]` depends on
  `yt-dlp[default]` (the scripts); install Deno with
  `curl -fsSL https://deno.land/install.sh | sh` (Deno is yt-dlp's default
  runtime; node or bun must be enabled via `extra_opts={'js_runtimes': ...}`).
  yb also finds Deno in `~/.deno/bin` when it is not on PATH. Run `yb check`
  (or `yb.download.check_requirements()`) to see what is missing.
- Downloading audio then feeding it to a podcast episode? Continue with
  **yb-podcast**. Publishing a video? See **yb-publish**.

# yb.download.youtube

Download YouTube videos (and their metadata) via yt-dlp.

The common case is one call — `download_youtube_video(url)` — which fetches
the best video+audio into `~/Downloads` as `Title (video_id).mp4`. Every
knob (destination, format, filename template, and which sidecar metadata to
also save) is overridable, and any raw yt-dlp option can be passed through.

The destination defaults to `$YB_DOWNLOAD_DIR` when set, else `~/Downloads`.

### Module Attributes

| [`OnConvertError`](#yb.download.youtube.OnConvertError)       | What [`download_youtube_audio()`](#yb.download.youtube.download_youtube_audio) does when a format conversion fails.     |
|-----------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------|
| [`DOWNLOAD_DIR_ENV`](#yb.download.youtube.DOWNLOAD_DIR_ENV)     | Env var that overrides the default download directory.                                                                  |
| [`COOKIES_FILE_ENV`](#yb.download.youtube.COOKIES_FILE_ENV)     | Env var naming a Netscape-format cookies file to authenticate downloads with.                                           |
| [`DEFAULT_COOKIES_FILE`](#yb.download.youtube.DEFAULT_COOKIES_FILE) | Cookies file used when [`COOKIES_FILE_ENV`](#yb.download.youtube.COOKIES_FILE_ENV) is unset and this file exists. |
| [`CookiesFile`](#yb.download.youtube.CookiesFile)          | a path, `None` (look for a default), or `False` (none).                                                                 |
| [`DEFAULT_OUTTMPL`](#yb.download.youtube.DEFAULT_OUTTMPL)      | human title plus the stable id, e.g. "My Talk (dQw4...).mp4".                                                           |
| [`DEFAULT_AUDIO_FMT`](#yb.download.youtube.DEFAULT_AUDIO_FMT)    | yt-dlp format selector for the best audio-only stream.                                                                  |

### Functions

| [`default_cookies_file`](#yb.download.youtube.default_cookies_file)()                         | The cookies file downloads use when none is passed, or `None`.                |
|-------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------|
| [`default_download_dir`](#yb.download.youtube.default_download_dir)()                         | Resolve the default download directory (`$YB_DOWNLOAD_DIR` or `~/Downloads`). |
| [`download_youtube_audio`](#yb.download.youtube.download_youtube_audio)(url, \*[, ...])         | Download only a video's audio (no video stream).                              |
| [`download_youtube_playlist`](#yb.download.youtube.download_youtube_playlist)(url, \*[, ...])      | Download all (or a selected subset of) a YouTube playlist's videos.           |
| [`download_youtube_video`](#yb.download.youtube.download_youtube_video)(url, \*[, ...])         | Download a YouTube video to `download_dir` (default `~/Downloads`).           |
| [`glob_escape`](#yb.download.youtube.glob_escape)(name)                              | Escape glob metacharacters in a literal filename stem.                        |
| [`youtube_playlist_info`](#yb.download.youtube.youtube_playlist_info)(url, \*[, ...])          | Fetch a playlist's per-video metadata without downloading.                    |
| [`youtube_video_info`](#yb.download.youtube.youtube_video_info)(url, \*[, extra_opts, ...]) | Fetch a video's metadata without downloading it.                              |

### Classes

| [`DownloadResult`](#yb.download.youtube.DownloadResult)(path, info[, sidecars])   | Outcome of a download.   |
|-------------------------------------------------------------------------------------------|--------------------------|

### yb.download.youtube.COOKIES_FILE_ENV *= 'YB_COOKIES_FILE'*

Env var naming a Netscape-format cookies file to authenticate downloads with.

### yb.download.youtube.CookiesFile

a path, `None` (look for a default), or `False` (none).

* **Type:**
  What `cookies_file` accepts

alias of [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path) | [`Literal`](https://docs.python.org/3/library/typing.html#typing.Literal)[False] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### yb.download.youtube.DEFAULT_AUDIO_FMT *= 'bestaudio/best'*

yt-dlp format selector for the best audio-only stream.

### yb.download.youtube.DEFAULT_COOKIES_FILE *= '~/.config/yb/youtube-cookies.txt'*

Cookies file used when [`COOKIES_FILE_ENV`](#yb.download.youtube.COOKIES_FILE_ENV) is unset and this file exists.

### yb.download.youtube.DEFAULT_OUTTMPL *= '%(title)s (%(id)s).%(ext)s'*

human title plus the stable id, e.g. “My Talk (dQw4…).mp4”.

* **Type:**
  yt-dlp output template

### yb.download.youtube.DOWNLOAD_DIR_ENV *= 'YB_DOWNLOAD_DIR'*

Env var that overrides the default download directory.

### *class* yb.download.youtube.DownloadResult(path, info, sidecars=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Outcome of a download.

#### path

The downloaded media file.

#### info

A trimmed metadata dict (see `_INFO_FIELDS`).

#### sidecars

Map of extra artifacts written (`info_json`, `thumbnail`,
`description`, `subtitles` → path(s)).

#### *property* video_id *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

The YouTube video id.

### yb.download.youtube.OnConvertError

What [`download_youtube_audio()`](#yb.download.youtube.download_youtube_audio) does when a format conversion fails.

alias of [`Literal`](https://docs.python.org/3/library/typing.html#typing.Literal)[‘raise’, ‘warn’]

### yb.download.youtube.default_cookies_file()

The cookies file downloads use when none is passed, or `None`.

`$YB_COOKIES_FILE` if set, else `~/.config/yb/youtube-cookies.txt` if it
exists. A file named by the env var that does not exist is skipped with a
warning (a typo should not silently fall back to anonymous downloads).

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### yb.download.youtube.default_download_dir()

Resolve the default download directory (`$YB_DOWNLOAD_DIR` or `~/Downloads`).

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### yb.download.youtube.download_youtube_audio(url, , download_dir=None, audio_format=None, bitrate=None, keep_original=False, on_error='raise', fmt='bestaudio/best', filename_template='%(title)s (%(id)s).%(ext)s', write_info_json=False, write_thumbnail=False, write_description=False, write_subtitles=False, write_auto_subtitles=False, subtitle_langs=('en',), quiet=True, extra_opts=None, start=None, end=None, precise_cuts=False, cookies_file=None)

Download only a video’s audio (no video stream).

Simplest use: `download_youtube_audio(url)` → the best audio stream, kept
in whatever format the source offers (YouTube’s is usually Opus in a
`.webm` container), named `Title (video_id).webm` in `~/Downloads`.

Pass `audio_format` to get a specific format instead:

```pycon
>>> download_youtube_audio(url, audio_format="mp3")
```

* **Parameters:**
  * **url** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The video URL (or id).
  * **download_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Destination directory. Defaults to
    [`default_download_dir()`](#yb.download.youtube.default_download_dir).
  * **audio_format** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Target format as an extension (`"mp3"`, `".wav"`, …).
    The default `None` means **no conversion** — keep the downloaded
    bytes exactly as they came, which needs no ffmpeg and avoids
    re-encoding a lossy stream into another lossy format.
  * **bitrate** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Bitrate for lossy targets (e.g. `"320k"`). Ignored when
    `audio_format` is lossless or `None`.
  * **keep_original** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – When converting, also keep the originally downloaded
    file (by default it is removed once converted).
  * **on_error** ([`Literal`](https://docs.python.org/3/library/typing.html#typing.Literal)[`'raise'`, `'warn'`]) – What to do when conversion fails (ffmpeg missing or erroring).
    `"raise"` (default) propagates
    [`AudioConversionError`](yb.audio_convert.html.md#yb.audio_convert.AudioConversionError); `"warn"` emits a
    warning and returns the unconverted download. Either way the
    downloaded audio is left on disk — a failed conversion never costs
    you the download.
  * **fmt** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – yt-dlp format selector (default best audio-only stream).
  * **filename_template** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – yt-dlp output template (default
    `"%(title)s (%(id)s).%(ext)s"`).
  * **write_info_json** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Also save the full metadata as `*.info.json`.
  * **write_thumbnail** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Also save the thumbnail image.
  * **write_description** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Also save the description as `*.description`.
  * **write_subtitles** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Also save uploaded subtitles for `subtitle_langs`.
  * **write_auto_subtitles** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Also save auto-generated subtitles.
  * **subtitle_langs** ([`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]) – Subtitle languages to fetch when subtitles are enabled.
  * **quiet** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Suppress yt-dlp console output.
  * **extra_opts** ([`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Any additional raw yt-dlp options (merged last, so they win).
  * **start** ([`int`](https://docs.python.org/3/builtins/functions.html#int) | [`float`](https://docs.python.org/3/builtins/functions.html#float) | [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – 

    Download only a span, as in
    [`download_youtube_video()`](#yb.download.youtube.download_youtube_video):
    ```pycon
    >>> download_youtube_audio(url, start="0:07.9", end="0:08.75")
    ```
  * **end** ([`int`](https://docs.python.org/3/builtins/functions.html#int) | [`float`](https://docs.python.org/3/builtins/functions.html#float) | [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – 

    Download only a span, as in
    [`download_youtube_video()`](#yb.download.youtube.download_youtube_video):
    ```pycon
    >>> download_youtube_audio(url, start="0:07.9", end="0:08.75")
    ```
  * **precise_cuts** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – 

    Download only a span, as in
    [`download_youtube_video()`](#yb.download.youtube.download_youtube_video):
    ```pycon
    >>> download_youtube_audio(url, start="0:07.9", end="0:08.75")
    ```
* **Return type:**
  [`DownloadResult`](#yb.download.youtube.DownloadResult)
* **Returns:**
  A [`DownloadResult`](#yb.download.youtube.DownloadResult) whose `path` is the audio file — converted
  when `audio_format` was given and conversion succeeded.
* **Raises:**
  * [**ValueError**](https://docs.python.org/3/builtins/exceptions.html#ValueError) – If `on_error` is not `"raise"` or `"warn"`.
  * [**AudioConversionError**](yb.audio_convert.html.md#yb.audio_convert.AudioConversionError) – If conversion fails and `on_error="raise"`.

### yb.download.youtube.download_youtube_playlist(url, , download_dir=None, playlist_items=None, skip_first=False, title_reject=None, download_archive=None, fmt='bestvideo+bestaudio/best', merge_to='mp4', filename_template='%(title)s (%(id)s).%(ext)s', write_info_json=True, write_thumbnail=False, write_description=False, write_subtitles=False, write_auto_subtitles=False, subtitle_langs=('en',), cookies_from_browser=None, extractor_args=None, quiet=True, extra_opts=None, cookies_file=None)

Download all (or a selected subset of) a YouTube playlist’s videos.

Simplest use: `download_youtube_playlist(url)` → every video downloaded best
quality merged to mp4 into `download_dir` (default `~/Downloads`), each with
its `*.info.json` sidecar (`write_info_json` defaults to `True` here, since
a playlist download is usually an archival operation).

Selecting a subset (yt-dlp `--playlist-items` is **1-based**):

> # skip the first (“PV”/intro) entry, keep the rest
> download_youtube_playlist(url, skip_first=True)         # -> playlist_items=”2:”
> download_youtube_playlist(url, playlist_items=”2:”)     # same, explicit
> download_youtube_playlist(url, playlist_items=”2”)      # only the 2nd video
> download_youtube_playlist(url, title_reject=”PV”)       # skip entries whose title contains “PV”
* **Parameters:**
  * **url** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The playlist URL.
  * **download_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Destination directory (default [`default_download_dir()`](#yb.download.youtube.default_download_dir)).
  * **playlist_items** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – yt-dlp item selector (1-based; `"2:"`, `"2"`, `"1:5,8"`).
  * **skip_first** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Convenience for `playlist_items="2:"` (ignored if
    `playlist_items` is given).
  * **title_reject** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Skip entries whose (case-insensitive) title contains this
    substring — more robust than a positional skip if ordering changes.
  * **download_archive** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Path to a yt-dlp archive file recording downloaded ids,
    making re-runs idempotent/resumable.
  * **fmt** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – yt-dlp format selector (default best video + best audio).
  * **merge_to** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Container to merge into (default `"mp4"`; needs ffmpeg).
  * **filename_template** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – yt-dlp output template (default
    `"%(title)s (%(id)s).%(ext)s"`).
  * **write_info_json** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Save each video’s `*.info.json` (default `True`).
  * **write_thumbnail** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool))
  * **write_description** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool))
  * **write_subtitles** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool))
  * **write_auto_subtitles** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool))
* **Return type:**
  [*list*](https://docs.python.org/3/builtins/stdtypes.html#list)[[*DownloadResult*](#yb.download.youtube.DownloadResult)]

:param :
:type subtitle_langs: [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]
:param subtitle_langs: As in [`download_youtube_video()`](#yb.download.youtube.download_youtube_video).
:type cookies_from_browser: [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple) | [`None`](https://docs.python.org/3/builtins/constants.html#None)
:param cookies_from_browser: Browser to read cookies from for bot-detection /

> age / region issues, e.g. `"safari"` or `("chrome", "Profile 1")`.
* **Parameters:**
  * **extractor_args** ([`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – yt-dlp `extractor_args` (e.g.
    `{"youtube": {"player_client": ["web_safari"]}}`).
  * **quiet** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Suppress yt-dlp console output.
  * **extra_opts** ([`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Any additional raw yt-dlp options (merged last, so they win).
  * **cookies_file** (`Union`[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path), [`Literal`](https://docs.python.org/3/library/typing.html#typing.Literal)[`False`], [`None`](https://docs.python.org/3/builtins/constants.html#None)]) – As in [`download_youtube_video()`](#yb.download.youtube.download_youtube_video); an explicit
    `cookies_from_browser` takes precedence over the default file.
* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`DownloadResult`](#yb.download.youtube.DownloadResult)]
* **Returns:**
  A list of [`DownloadResult`](#yb.download.youtube.DownloadResult), one per successfully-downloaded entry,
  in playlist order. Entries skipped by selection/filter or that failed
  (under `ignoreerrors`) are omitted.

### yb.download.youtube.download_youtube_video(url, , download_dir=None, fmt='bestvideo+bestaudio/best', merge_to='mp4', filename_template='%(title)s (%(id)s).%(ext)s', write_info_json=False, write_thumbnail=False, write_description=False, write_subtitles=False, write_auto_subtitles=False, subtitle_langs=('en',), quiet=True, extra_opts=None, start=None, end=None, precise_cuts=False, cookies_file=None)

Download a YouTube video to `download_dir` (default `~/Downloads`).

Simplest use: `download_youtube_video(url)` → best quality merged to mp4,
named `Title (video_id).mp4` in `~/Downloads`.

* **Parameters:**
  * **url** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The video URL (or id).
  * **download_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Destination directory. Defaults to
    [`default_download_dir()`](#yb.download.youtube.default_download_dir).
  * **fmt** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – yt-dlp format selector (default best video + best audio).
  * **merge_to** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Container to merge video+audio into (default `"mp4"`;
    requires ffmpeg). Set `None` to keep yt-dlp’s default.
  * **filename_template** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – yt-dlp output template (default
    `"%(title)s (%(id)s).%(ext)s"`).
  * **write_info_json** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Also save the full metadata as `*.info.json`.
  * **write_thumbnail** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Also save the thumbnail image.
  * **write_description** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Also save the description as `*.description`.
  * **write_subtitles** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Also save uploaded subtitles for `subtitle_langs`.
  * **write_auto_subtitles** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Also save auto-generated subtitles.
  * **subtitle_langs** ([`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]) – Subtitle languages to fetch when subtitles are enabled.
  * **quiet** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Suppress yt-dlp console output.
  * **extra_opts** ([`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Any additional raw yt-dlp options (merged last, so they win).
  * **start** ([`int`](https://docs.python.org/3/builtins/functions.html#int) | [`float`](https://docs.python.org/3/builtins/functions.html#float) | [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Download only this span: seconds (`7.9`) or a timestamp
    (`"0:07.9"`, `"1:02:03"`). Either may be given alone (`end`
    only = from the beginning; `start` only = to the end). The span
    is recorded in `info["download_range"]` as `{"start", "end"}`
    seconds (`end` is `None` for “to the end”), and, with the
    default `filename_template`, in the filename (`Title (id)
    [7.9-8.75].mp4`) so a clip never collides with the full video.
    Needs ffmpeg (see [`yb.download.ranges`](yb.download.ranges.html.md#module-yb.download.ranges)).
  * **end** ([`int`](https://docs.python.org/3/builtins/functions.html#int) | [`float`](https://docs.python.org/3/builtins/functions.html#float) | [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Download only this span: seconds (`7.9`) or a timestamp
    (`"0:07.9"`, `"1:02:03"`). Either may be given alone (`end`
    only = from the beginning; `start` only = to the end). The span
    is recorded in `info["download_range"]` as `{"start", "end"}`
    seconds (`end` is `None` for “to the end”), and, with the
    default `filename_template`, in the filename (`Title (id)
    [7.9-8.75].mp4`) so a clip never collides with the full video.
    Needs ffmpeg (see [`yb.download.ranges`](yb.download.ranges.html.md#module-yb.download.ranges)).
  * **precise_cuts** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – With `start`/`end`, re-encode at the cuts for
    frame-accurate bounds (slower) instead of cutting at keyframes.
  * **cookies_file** (`Union`[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path), [`Literal`](https://docs.python.org/3/library/typing.html#typing.Literal)[`False`], [`None`](https://docs.python.org/3/builtins/constants.html#None)]) – Netscape-format cookies file to authenticate with (for
    headless servers where `cookies_from_browser` cannot work). Default
    `None` reads `$YB_COOKIES_FILE`, else
    `~/.config/yb/youtube-cookies.txt` if it exists, else sends no
    cookies. An explicit `cookies_from_browser` or `extra_opts`
    cookie option suppresses that default; `False` opts out of it.
    The file is checked first (`ValueError` if explicit, else a
    warning, naming only line numbers). It cannot be combined with a
    browser cookie source. yt-dlp rewrites the file with refreshed
    cookies on exit, so it must be writable and not shared by parallel
    workers.
* **Return type:**
  [`DownloadResult`](#yb.download.youtube.DownloadResult)
* **Returns:**
  A [`DownloadResult`](#yb.download.youtube.DownloadResult) with the media path, trimmed `info`, and any
  `sidecars` written.
* **Raises:**
  [**ValueError**](https://docs.python.org/3/builtins/exceptions.html#ValueError) – If `start`/`end` is not a timestamp, or `end` is not
      after `start`. Raised before anything is fetched or written.

### yb.download.youtube.glob_escape(name)

Escape glob metacharacters in a literal filename stem.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### yb.download.youtube.youtube_playlist_info(url, , playlist_items=None, flat=True, extra_opts=None, cookies_file=None)

Fetch a playlist’s per-video metadata without downloading.

Returns a dict with playlist-level fields (`playlist_id`, `playlist_title`,
`webpage_url`, `uploader`, `count`) and an `entries` list. With
`flat=True` (default) extraction is fast/shallow (each entry has at least
`id`, `title`, `url`); with `flat=False` each entry is fully resolved
and trimmed to `_INFO_FIELDS` (slower, but includes duration/fps/etc.).

* **Parameters:**
  * **url** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The playlist URL.
  * **playlist_items** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – yt-dlp `--playlist-items` selector, 1-based, e.g.
    `"2:"` (all but the first), `"2"` (only the 2nd), `"1:5,8"`.
  * **flat** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Shallow vs full per-entry extraction.
  * **extra_opts** ([`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Additional raw yt-dlp options (merged last).
  * **cookies_file** (`Union`[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path), [`Literal`](https://docs.python.org/3/library/typing.html#typing.Literal)[`False`], [`None`](https://docs.python.org/3/builtins/constants.html#None)]) – See [`download_youtube_video()`](#yb.download.youtube.download_youtube_video).
* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### yb.download.youtube.youtube_video_info(url, , extra_opts=None, cookies_file=None)

Fetch a video’s metadata without downloading it.

Returns the trimmed info dict (see `_INFO_FIELDS`). Useful to preview
the title/duration/chapters before deciding to download.

`cookies_file`: see [`download_youtube_video()`](#yb.download.youtube.download_youtube_video).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

# yb.download

Media download (yt-dlp) — fetch videos, audio, and their metadata.

A separate, optionally-installed module (`pip install 'yb[download]'`).
Common use:

```pycon
>>> from yb.download import download_youtube_video
>>> result = download_youtube_video("https://youtu.be/PRa9ciOe-us")
>>> print(result.path, result.video_id)
```

For audio only — e.g. to feed a transcription or podcast workflow — use
[`download_youtube_audio()`](#yb.download.download_youtube_audio), which keeps the source format by default and
converts only when you ask it to (conversion needs ffmpeg):

```pycon
>>> from yb.download import download_youtube_audio
>>> ep = download_youtube_audio(url, audio_format="mp3")
```

For sound or clip sourcing, fetch just a span (seconds or `"mm:ss"`; needs
ffmpeg, see [`yb.download.ranges`](yb.download.ranges.html.md#module-yb.download.ranges)). The span is recorded in
`result.info["download_range"]` for provenance:

```pycon
>>> clip = download_youtube_audio(url, start="0:07.9", end="0:08.75")
```

To go from a name to a download, search first ([`search_youtube()`](#yb.download.search_youtube)):

```pycon
>>> from yb.download import search_youtube
>>> hits = search_youtube("hanuman chalisa", limit=3)
>>> download_youtube_audio(hits[0].url)
```

YouTube downloads need a JavaScript runtime (Deno) and yt-dlp’s solver
scripts; [`check_requirements()`](#yb.download.check_requirements) (or `yb check`) says what’s missing and
how to install it. The first download in a process runs it and warns.

### Functions

| [`download_youtube_video`](#yb.download.download_youtube_video)(url, \*[, ...])         | Download a YouTube video to `download_dir` (default `~/Downloads`).           |
|-------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------|
| [`download_youtube_audio`](#yb.download.download_youtube_audio)(url, \*[, ...])         | Download only a video's audio (no video stream).                              |
| [`youtube_video_info`](#yb.download.youtube_video_info)(url, \*[, extra_opts, ...]) | Fetch a video's metadata without downloading it.                              |
| [`download_youtube_playlist`](#yb.download.download_youtube_playlist)(url, \*[, ...])      | Download all (or a selected subset of) a YouTube playlist's videos.           |
| [`youtube_playlist_info`](#yb.download.youtube_playlist_info)(url, \*[, ...])          | Fetch a playlist's per-video metadata without downloading.                    |
| [`search_youtube`](#yb.download.search_youtube)(query, \*[, limit, ...])        | Search YouTube by name; returns up to `limit` hits, best match first.         |
| [`default_download_dir`](#yb.download.default_download_dir)()                         | Resolve the default download directory (`$YB_DOWNLOAD_DIR` or `~/Downloads`). |
| [`convert_audio`](#yb.download.convert_audio)(src, audio_format, \*[, ...])    | Convert `src` to `audio_format`, returning the resulting path.                |
| [`check_requirements`](#yb.download.check_requirements)(\*[, warn, which, ...])     | Check what YouTube downloads need, and say how to fix what's missing.         |
| [`find_js_runtime`](#yb.download.find_js_runtime)(\*[, which, search_dirs])      | Find Deno on `PATH`, else in its standard install location.                   |
| [`parse_timestamp`](#yb.download.parse_timestamp)(value)                         | Seconds from a number or a `"[[h:]m:]s[.fraction]"` string.                   |

### Classes

| [`SearchHit`](#yb.download.SearchHit)(id, title, duration, channel, url)    | One row of [`search_youtube()`](#yb.download.search_youtube) (flat extraction: no per-video fetch).   |
|--------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------|
| [`DownloadResult`](#yb.download.DownloadResult)(path, info[, sidecars])          | Outcome of a download.                                                                                                |
| [`JsRuntime`](#yb.download.JsRuntime)(name, path, on_path)                  | A JavaScript runtime found for yt-dlp.                                                                                |
| [`Pace`](#yb.download.Pace)([sleep_interval, max_sleep_interval, ...]) | How gently to talk to YouTube.                                                                                        |
| [`TimeRange`](#yb.download.TimeRange)([start, end])                         | A span of a video, in seconds.                                                                                        |

### Exceptions

| [`AudioConversionError`](#yb.download.AudioConversionError)       | Raised when audio could not be converted to the requested format.            |
|-----------------------------------------------------------------------------|------------------------------------------------------------------------------|
| [`DownloadRequirementWarning`](#yb.download.DownloadRequirementWarning) | A download prerequisite (JS runtime, solver scripts) looks missing.          |
| [`RateLimitedError`](#yb.download.RateLimitedError)           | YouTube refused the request (HTTP 429 or a "confirm you're not a bot" wall). |

### *exception* yb.download.AudioConversionError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

Raised when audio could not be converted to the requested format.

### *exception* yb.download.DownloadRequirementWarning

Bases: [`UserWarning`](https://docs.python.org/3/builtins/exceptions.html#UserWarning)

A download prerequisite (JS runtime, solver scripts) looks missing.

### *class* yb.download.DownloadResult(path, info, sidecars=dict())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Outcome of a download.

#### path

The downloaded media file.

* **Type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

#### info

A trimmed metadata dict (see `_INFO_FIELDS`).

* **Type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

#### sidecars

Map of extra artifacts written (`info_json`, `thumbnail`,
`description`, `subtitles` → path(s)).

* **Type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

#### *property* video_id *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

The YouTube video id.

### *class* yb.download.JsRuntime(name, path, on_path)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A JavaScript runtime found for yt-dlp.

#### name

yt-dlp’s key for the runtime (e.g. `"deno"`).

* **Type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

#### path

The executable.

* **Type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

#### on_path

Whether yt-dlp would find it by name on `PATH` unaided.

* **Type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### *class* yb.download.Pace(sleep_interval=None, max_sleep_interval=None, sleep_requests=None, limit_rate=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

How gently to talk to YouTube.

#### sleep_interval

Seconds to sleep before each download (yt-dlp
`sleep_interval`); with `max_sleep_interval` a random value in
between is used.

* **Type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### max_sleep_interval

Upper bound of the random sleep.

* **Type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### sleep_requests

Seconds to sleep between metadata requests
(yt-dlp `sleep_interval_requests`).

* **Type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### limit_rate

Maximum download rate, e.g. `"4M"` or `"500K"` (bytes/s).

* **Type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### *exception* yb.download.RateLimitedError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

YouTube refused the request (HTTP 429 or a “confirm you’re not a bot” wall).

### *class* yb.download.SearchHit(id, title, duration, channel, url)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One row of [`search_youtube()`](#yb.download.search_youtube) (flat extraction: no per-video fetch).

`duration` is in seconds and may be `None` (live streams, some results).

### *class* yb.download.TimeRange(start=0.0, end=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A span of a video, in seconds. `end=None` means “to the end”.

#### as_info()

The span as recorded on a result’s `info` (for provenance).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`float`](https://docs.python.org/3/builtins/functions.html#float) | [`None`](https://docs.python.org/3/builtins/constants.html#None)]

#### *property* label *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

`"7.9-8.75"` or `"30-end"`.

* **Type:**
  Compact, filename-safe form

#### *classmethod* of(, start=None, end=None)

Build from user input; `None` when neither bound is given.

* **Raises:**
  [**ValueError**](https://docs.python.org/3/builtins/exceptions.html#ValueError) – On a bad timestamp, or `end` not after `start`.
* **Return type:**
  [`TimeRange`](yb.download.ranges.html.md#yb.download.ranges.TimeRange) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### yb.download.check_requirements(\*, warn=True, which=<function which>, search_dirs=None, find_spec=<function find_spec>, run=<function run>, import_module=<function import_module>, check_deno_version=True)

Check what YouTube downloads need, and say how to fix what’s missing.

Never raises. Each problem is a message ending with the fix.

* **Parameters:**
  * **warn** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Also emit each problem as a [`DownloadRequirementWarning`](#yb.download.DownloadRequirementWarning).
  * **which** ([`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)]) – See [`find_js_runtime()`](#yb.download.find_js_runtime).
  * **search_dirs** ([`Iterable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterable)[[`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – See [`find_js_runtime()`](#yb.download.find_js_runtime).
  * **find_spec** ([`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`object`](https://docs.python.org/3/builtins/functions.html#object) | [`None`](https://docs.python.org/3/builtins/constants.html#None)]) – Module lookup for `has_module()`.
  * **run** ([`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis), [`CompletedProcess`](https://docs.python.org/3/library/subprocess.html#subprocess.CompletedProcess)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]) – Subprocess runner for `deno_version()`.
  * **import_module** ([`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`object`](https://docs.python.org/3/builtins/functions.html#object)]) – Importer for `min_deno_version()`.
  * **check_deno_version** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Also run `deno --version` and compare it with
    yt-dlp’s minimum. The download preflight turns this off: it spawns
    a process, which belongs in an explicit check, not in a download.
* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
* **Returns:**
  The problems found; empty when downloads should work.

### yb.download.convert_audio(src, audio_format, , output=None, bitrate=None, overwrite=True, extra_ffmpeg_args=())

Convert `src` to `audio_format`, returning the resulting path.

* **Parameters:**
  * **src** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – The audio file to convert.
  * **audio_format** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Target format as an extension (`"mp3"`, `".wav"`, …).
  * **output** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Destination path. Defaults to `src` with the new extension.
  * **bitrate** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Target bitrate for lossy formats (e.g. `"320k"`). Defaults to
    `DEFAULT_LOSSY_BITRATE`; ignored for `LOSSLESS_FORMATS`.
  * **overwrite** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Overwrite `output` if it already exists.
  * **extra_ffmpeg_args** ([`Iterable`](https://docs.python.org/3/library/typing.html#typing.Iterable)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Raw ffmpeg arguments, appended last so they win.
* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)
* **Returns:**
  The converted file’s path — or `src` unchanged when it is already in
  the target format (no pointless re-encode, no generation loss).
* **Raises:**
  * [**FileNotFoundError**](https://docs.python.org/3/builtins/exceptions.html#FileNotFoundError) – If `src` does not exist.
  * [**AudioConversionError**](#yb.download.AudioConversionError) – If ffmpeg is missing, or the conversion fails.

### yb.download.default_download_dir()

Resolve the default download directory (`$YB_DOWNLOAD_DIR` or `~/Downloads`).

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### yb.download.download_youtube_audio(url, , download_dir=None, audio_format=None, bitrate=None, keep_original=False, on_error='raise', fmt='bestaudio/best', filename_template='%(title)s (%(id)s).%(ext)s', write_info_json=False, write_thumbnail=False, write_description=False, write_subtitles=False, write_auto_subtitles=False, subtitle_langs=('en',), quiet=True, extra_opts=None, start=None, end=None, precise_cuts=False, cookies_file=None, pace=None)

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
    [`default_download_dir()`](#yb.download.default_download_dir).
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
  * **pace** ([`Pace`](yb.download.pacing.html.md#yb.download.pacing.Pace) | [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – As in [`download_youtube_video()`](#yb.download.download_youtube_video).
  * **start** ([`int`](https://docs.python.org/3/builtins/functions.html#int) | [`float`](https://docs.python.org/3/builtins/functions.html#float) | [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – 

    Download only a span, as in
    [`download_youtube_video()`](#yb.download.download_youtube_video):
    ```pycon
    >>> download_youtube_audio(url, start="0:07.9", end="0:08.75")
    ```
  * **end** ([`int`](https://docs.python.org/3/builtins/functions.html#int) | [`float`](https://docs.python.org/3/builtins/functions.html#float) | [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – 

    Download only a span, as in
    [`download_youtube_video()`](#yb.download.download_youtube_video):
    ```pycon
    >>> download_youtube_audio(url, start="0:07.9", end="0:08.75")
    ```
  * **precise_cuts** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – 

    Download only a span, as in
    [`download_youtube_video()`](#yb.download.download_youtube_video):
    ```pycon
    >>> download_youtube_audio(url, start="0:07.9", end="0:08.75")
    ```
* **Return type:**
  [`DownloadResult`](yb.download.youtube.html.md#yb.download.youtube.DownloadResult)
* **Returns:**
  A [`DownloadResult`](#yb.download.DownloadResult) whose `path` is the audio file — converted
  when `audio_format` was given and conversion succeeded.
* **Raises:**
  * [**ValueError**](https://docs.python.org/3/builtins/exceptions.html#ValueError) – If `on_error` is not `"raise"` or `"warn"`.
  * [**AudioConversionError**](#yb.download.AudioConversionError) – If conversion fails and `on_error="raise"`.

### yb.download.download_youtube_playlist(url, , download_dir=None, playlist_items=None, skip_first=False, title_reject=None, download_archive=None, fmt='bestvideo+bestaudio/best', merge_to='mp4', filename_template='%(title)s (%(id)s).%(ext)s', write_info_json=True, write_thumbnail=False, write_description=False, write_subtitles=False, write_auto_subtitles=False, subtitle_langs=('en',), cookies_from_browser=None, extractor_args=None, quiet=True, extra_opts=None, cookies_file=None, pace=None, item_folders=False, embed_metadata=False)

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
  * **download_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Destination directory (default [`default_download_dir()`](#yb.download.default_download_dir)).
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
  [*list*](https://docs.python.org/3/builtins/stdtypes.html#list)[[*DownloadResult*](yb.download.youtube.html.md#yb.download.youtube.DownloadResult)]

:param :
:type subtitle_langs: [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]
:param subtitle_langs: As in [`download_youtube_video()`](#yb.download.download_youtube_video).
:type cookies_from_browser: [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple) | [`None`](https://docs.python.org/3/builtins/constants.html#None)
:param cookies_from_browser: Browser to read cookies from for bot-detection /

> age / region issues, e.g. `"safari"` or `("chrome", "Profile 1")`.
* **Parameters:**
  * **extractor_args** ([`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – yt-dlp `extractor_args` (e.g.
    `{"youtube": {"player_client": ["web_safari"]}}`).
  * **quiet** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Suppress yt-dlp console output.
  * **extra_opts** ([`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Any additional raw yt-dlp options (merged last, so they win).
  * **cookies_file** ([`Union`](https://docs.python.org/3/library/typing.html#typing.Union)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path), [`Literal`](https://docs.python.org/3/library/typing.html#typing.Literal)[[`False`](https://docs.python.org/3/builtins/constants.html#False)], [`None`](https://docs.python.org/3/builtins/constants.html#None)]) – As in [`download_youtube_video()`](#yb.download.download_youtube_video); an explicit
    `cookies_from_browser` takes precedence over the default file.
  * **pace** ([`Pace`](yb.download.pacing.html.md#yb.download.pacing.Pace) | [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Be gentle with YouTube: a [`Pace`](yb.download.pacing.html.md#yb.download.pacing.Pace) or a
    preset name (`"polite"`: sleep 20-60 s between items, 1 s between
    requests, 4 MB/s cap). Default `None` adds nothing. Raw yt-dlp
    options in `extra_opts` win over it.
  * **item_folders** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Put each item in its own folder `001_<id>/<id>.<ext>`
    (the number is the 1-based playlist position, stable under
    `playlist_items`), sidecars beside it under flat id-keyed names.
    Incompatible with a custom `filename_template`.
  * **embed_metadata** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Write title/artist/etc. into the media file (yt-dlp
    `--embed-metadata`; needs ffmpeg).
* **Return type:**
  [*list*](https://docs.python.org/3/builtins/stdtypes.html#list)[[*DownloadResult*](yb.download.youtube.html.md#yb.download.youtube.DownloadResult)]

Audio only: pass `fmt="bestaudio/best", merge_to=None` (keeps the source
stream, e.g. `.m4a`, without re-encoding).

* **Raises:**
  [**RateLimitedError**](#yb.download.RateLimitedError) – On HTTP 429 or a “confirm you’re not a bot” wall, with
      a backoff hint. (Per-item failures under `ignoreerrors` are skipped.)
* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`DownloadResult`](yb.download.youtube.html.md#yb.download.youtube.DownloadResult)]
* **Returns:**
  A list of [`DownloadResult`](#yb.download.DownloadResult), one per successfully-downloaded entry,
  in playlist order. Entries skipped by selection/filter or that failed
  (under `ignoreerrors`) are omitted.

### yb.download.download_youtube_video(url, , download_dir=None, fmt='bestvideo+bestaudio/best', merge_to='mp4', filename_template='%(title)s (%(id)s).%(ext)s', write_info_json=False, write_thumbnail=False, write_description=False, write_subtitles=False, write_auto_subtitles=False, subtitle_langs=('en',), quiet=True, extra_opts=None, start=None, end=None, precise_cuts=False, cookies_file=None, pace=None)

Download a YouTube video to `download_dir` (default `~/Downloads`).

Simplest use: `download_youtube_video(url)` → best quality merged to mp4,
named `Title (video_id).mp4` in `~/Downloads`.

* **Parameters:**
  * **url** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The video URL (or id).
  * **download_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Destination directory. Defaults to
    [`default_download_dir()`](#yb.download.default_download_dir).
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
  * **cookies_file** ([`Union`](https://docs.python.org/3/library/typing.html#typing.Union)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path), [`Literal`](https://docs.python.org/3/library/typing.html#typing.Literal)[[`False`](https://docs.python.org/3/builtins/constants.html#False)], [`None`](https://docs.python.org/3/builtins/constants.html#None)]) – Netscape-format cookies file to authenticate with (for
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
  * **pace** ([`Pace`](yb.download.pacing.html.md#yb.download.pacing.Pace) | [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Be gentle with YouTube: a [`Pace`](yb.download.pacing.html.md#yb.download.pacing.Pace) or a
    preset name (`"polite"`: sleep 20-60 s between items, 1 s between
    requests, 4 MB/s cap). Default `None` adds nothing. Raw yt-dlp
    options in `extra_opts` win over it.
* **Return type:**
  [`DownloadResult`](yb.download.youtube.html.md#yb.download.youtube.DownloadResult)
* **Returns:**
  A [`DownloadResult`](#yb.download.DownloadResult) with the media path, trimmed `info`, and any
  `sidecars` written.
* **Raises:**
  [**ValueError**](https://docs.python.org/3/builtins/exceptions.html#ValueError) – If `start`/`end` is not a timestamp, or `end` is not
      after `start`. Raised before anything is fetched or written.

### yb.download.find_js_runtime(\*, which=<function which>, search_dirs=None)

Find Deno on `PATH`, else in its standard install location.

* **Parameters:**
  * **which** ([`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)]) – `PATH` lookup (injectable for tests).
  * **search_dirs** ([`Iterable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterable)[[`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Extra directories to look in when it isn’t on `PATH`
    (default `deno_search_dirs()`).
* **Return type:**
  [`JsRuntime`](yb.download.requirements.html.md#yb.download.requirements.JsRuntime) | [`None`](https://docs.python.org/3/builtins/constants.html#None)
* **Returns:**
  The runtime found, or `None`.

### yb.download.parse_timestamp(value)

Seconds from a number or a `"[[h:]m:]s[.fraction]"` string.

* **Raises:**
  [**ValueError**](https://docs.python.org/3/builtins/exceptions.html#ValueError) – If `value` is negative, not finite, or not a timestamp.
* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### yb.download.search_youtube(query, , limit=5, extra_opts=None, cookies_file=None)

Search YouTube by name; returns up to `limit` hits, best match first.

Hand a hit’s `url` to [`download_youtube_audio()`](#yb.download.download_youtube_audio) /
[`download_youtube_video()`](#yb.download.download_youtube_video):

```pycon
>>> hits = search_youtube("हनुमान चालीसा हरिहरन", limit=6)
>>> download_youtube_audio(hits[0].url)
```

Uses yt-dlp’s `ytsearchN:` with flat extraction (one request, no per-video
fetch), sharing the cookie and JS-runtime handling of the downloads.

* **Parameters:**
  * **query** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – What to search for (any script).
  * **limit** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – How many results, 1..:data:`MAX_SEARCH_LIMIT`.
  * **extra_opts** ([`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Additional raw yt-dlp options (merged last).
  * **cookies_file** ([`Union`](https://docs.python.org/3/library/typing.html#typing.Union)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path), [`Literal`](https://docs.python.org/3/library/typing.html#typing.Literal)[[`False`](https://docs.python.org/3/builtins/constants.html#False)], [`None`](https://docs.python.org/3/builtins/constants.html#None)]) – See [`download_youtube_video()`](#yb.download.download_youtube_video).
* **Raises:**
  [**ValueError**](https://docs.python.org/3/builtins/exceptions.html#ValueError) – If `query` is blank or `limit` is out of range.
* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`SearchHit`](yb.download.youtube.html.md#yb.download.youtube.SearchHit)]

### yb.download.youtube_playlist_info(url, , playlist_items=None, flat=True, extra_opts=None, cookies_file=None)

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
  * **cookies_file** ([`Union`](https://docs.python.org/3/library/typing.html#typing.Union)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path), [`Literal`](https://docs.python.org/3/library/typing.html#typing.Literal)[[`False`](https://docs.python.org/3/builtins/constants.html#False)], [`None`](https://docs.python.org/3/builtins/constants.html#None)]) – See [`download_youtube_video()`](#yb.download.download_youtube_video).
* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### yb.download.youtube_video_info(url, , extra_opts=None, cookies_file=None)

Fetch a video’s metadata without downloading it.

Returns the trimmed info dict (see `_INFO_FIELDS`). Useful to preview
the title/duration/chapters before deciding to download.

`cookies_file`: see [`download_youtube_video()`](#yb.download.download_youtube_video).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### Modules

| [`pacing`](yb.download.pacing.html.md#module-yb.download.pacing)             | Polite pacing for yt-dlp downloads, and a useful message when YouTube pushes back.   |
|-----------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------|
| [`ranges`](yb.download.ranges.html.md#module-yb.download.ranges)             | Download just a time range of a video: parse start/end, build yt-dlp's options.      |
| [`requirements`](yb.download.requirements.html.md#module-yb.download.requirements) | Preflight for downloading: does yt-dlp have what YouTube now demands?                |
| [`youtube`](yb.download.youtube.html.md#module-yb.download.youtube)           | Download YouTube videos (and their metadata) via yt-dlp.                             |

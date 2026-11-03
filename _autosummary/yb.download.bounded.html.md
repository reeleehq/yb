# yb.download.bounded

Link-to-audio with the safety policy applied once: [`download_audio_bounded()`](#yb.download.bounded.download_audio_bounded).

A service that turns a user-supplied link into an audio file (an MCP tool, an
ingest endpoint) needs the same guard rails every time: refuse bad targets before
touching the network, check every URL yt-dlp then requests (not only the first),
refuse over-long sources before fetching a byte, cap the bytes and the wall-clock
time even when the size is unknown, always produce mp3, send no ambient cookies,
and carry a copyright notice with the file. That policy lives here so a second
consumer does not copy it.

The caps are keyword-only arguments, and they are written *after* any caller
`extra_opts`, so a configured yt-dlp option (credentials, cookies, proxies)
can never widen them.

```pycon
>>> from yb.download import download_audio_bounded
>>> got = download_audio_bounded(url, max_bytes=60 * 2**20, max_duration_s=45 * 60)
>>> got.path, got.title, got.duration_s, got.notice
```

### Module Attributes

| [`DEFAULT_MAX_BYTES`](#yb.download.bounded.DEFAULT_MAX_BYTES)      | Default byte cap.                                                                                |
|-------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------|
| [`DEFAULT_MAX_DURATION_S`](#yb.download.bounded.DEFAULT_MAX_DURATION_S) | Default duration cap, in seconds (refuses livestream-length and multi-hour sources).             |
| [`DEFAULT_TIMEOUT_S`](#yb.download.bounded.DEFAULT_TIMEOUT_S)      | Default wall-clock budget for the whole call (metadata, download, conversion start), in seconds. |
| [`GUARDED_PROTOCOLS`](#yb.download.bounded.GUARDED_PROTOCOLS)      | Media protocols whose bytes yt-dlp fetches itself (through the request guard).                   |
| [`AUDIO_CODEC`](#yb.download.bounded.AUDIO_CODEC)            | Output codec and quality handed to yt-dlp's audio extractor.                                     |
| [`COPYRIGHT_NOTICE`](#yb.download.bounded.COPYRIGHT_NOTICE)       | Travels with every download (store it next to the file).                                         |
| [`DEPLOYMENT_OPT_KEYS`](#yb.download.bounded.DEPLOYMENT_OPT_KEYS)    | how to reach and authenticate to the source, nothing about what is fetched or where it goes.     |
| [`TargetValidator`](#yb.download.bounded.TargetValidator)        | raises `ValueError` to refuse `url`.                                                             |

### Functions

| [`download_audio_bounded`](#yb.download.bounded.download_audio_bounded)(url, \*, download_dir)   | Download the audio of one video link as mp3, refusing what exceeds the caps.   |
|--------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| [`require_http_url`](#yb.download.bounded.require_http_url)(url)                           | Default target check: an http(s) URL with a host.                              |

### Classes

| [`AudioDownload`](#yb.download.bounded.AudioDownload)(path, title, duration_s, ...)   | A bounded audio download.   |
|------------------------------------------------------------------------------------------------|-----------------------------|

### Exceptions

| [`AudioLimitError`](#yb.download.bounded.AudioLimitError)   | The source exceeds a cap (duration, size or time); nothing is left on disk.   |
|--------------------------------------------------------------------|-------------------------------------------------------------------------------|
| [`AudioSourceError`](#yb.download.bounded.AudioSourceError)  | yt-dlp could not get audio from the link (unsupported, unavailable, ...).     |
| [`AudioTargetError`](#yb.download.bounded.AudioTargetError)  | `validate_target` refused a URL: the link, or one yt-dlp was about to fetch.  |

### yb.download.bounded.AUDIO_CODEC *= 'mp3'*

Output codec and quality handed to yt-dlp’s audio extractor.

### *class* yb.download.bounded.AudioDownload(path, title, duration_s, notice, info)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A bounded audio download.

#### path

The mp3 file, alone in its own directory. The caller owns the
directory (`path.parent`): move the file, then remove it.

* **Type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

#### title

The source’s title, or the file stem when it has none.

* **Type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

#### duration_s

Length in seconds, `None` when the source did not say.

* **Type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### notice

The copyright notice to store with the file.

* **Type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

#### info

Trimmed source metadata (see `DownloadResult.info`).

* **Type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### *exception* yb.download.bounded.AudioLimitError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

The source exceeds a cap (duration, size or time); nothing is left on disk.

### *exception* yb.download.bounded.AudioSourceError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

yt-dlp could not get audio from the link (unsupported, unavailable, …).

### *exception* yb.download.bounded.AudioTargetError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

`validate_target` refused a URL: the link, or one yt-dlp was about to fetch.

### yb.download.bounded.COPYRIGHT_NOTICE *= "Downloaded from a user-supplied link — respect the source's copyright and terms of service; you are responsible for having the right to use it."*

Travels with every download (store it next to the file).

### yb.download.bounded.DEFAULT_MAX_BYTES *= 83886080*

Default byte cap. Above the mp3 size of a source at the default duration cap
(45 min at 192 kbps is about 65 MB), so a source that passes one passes both.

### yb.download.bounded.DEFAULT_MAX_DURATION_S *= 2700*

Default duration cap, in seconds (refuses livestream-length and multi-hour sources).

### yb.download.bounded.DEFAULT_TIMEOUT_S *= 600*

Default wall-clock budget for the whole call (metadata, download, conversion
start), in seconds. Bounds a stream that trickles bytes under every other cap.

### yb.download.bounded.DEPLOYMENT_OPT_KEYS *= frozenset({'cookiefile', 'cookiesfrombrowser', 'extractor_args', 'http_headers', 'js_runtimes', 'logger', 'password', 'proxy', 'remote_components', 'source_address', 'username'})*

how to reach and
authenticate to the source, nothing about what is fetched or where it goes.

* **Type:**
  yt-dlp options a deployment may pass in `extra_opts`

### yb.download.bounded.GUARDED_PROTOCOLS *= ('https', 'http', 'm3u8_native', 'http_dash_segments')*

Media protocols whose bytes yt-dlp fetches itself (through the request guard).
Others (rtmp, rtsp, ffmpeg-only `m3u8`, …) are handed to an external
program that the guard cannot see, so their formats are never selected.

### yb.download.bounded.TargetValidator

raises `ValueError` to refuse `url`.

* **Type:**
  A target check

alias of [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`None`](https://docs.python.org/3/builtins/constants.html#None)]

### yb.download.bounded.download_audio_bounded(url, \*, download_dir, max_bytes=83886080, max_duration_s=2700, timeout_s=600, validate_target=<function require_http_url>, extra_opts=None, cookies_file=False, notice="Downloaded from a user-supplied link — respect the source's copyright and terms of service; you are responsible for having the right to use it.")

Download the audio of one video link as mp3, refusing what exceeds the caps.

Order: `validate_target` on `url` (before any network); one yt-dlp
session whose every request (page, embedded page, manifest, media, fragment)
passes `validate_target` first, and whose final URL after redirects does
too; a metadata pass that refuses playlists, live streams and over-long
sources before any media bytes; the download of those same formats (no
second extraction), aborted past `max_bytes` or `timeout_s` even when
the size is unknown; a size check on the extracted file. The mp3 is written
to a fresh private directory under `download_dir` (so concurrent calls
never collide); on any failure that directory is removed.

* **Parameters:**
  * **url** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – A page link (YouTube, SoundCloud, Bandcamp, …).
  * **download_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – Parent of the per-call directory holding the mp3 (the caller
    owns that directory from then on and removes it after ingest).
  * **max_bytes** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – Cap on the downloaded and on the extracted file.
  * **max_duration_s** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – Cap on the source’s duration. A source that reports no
    duration passes this check and is bounded by `max_bytes` and
    `timeout_s`.
  * **timeout_s** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – Wall-clock budget for fetching, checked on every request and
    every received chunk (a stalled connection is bounded by yt-dlp’s
    socket timeout).
  * **validate_target** ([`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`None`](https://docs.python.org/3/builtins/constants.html#None)]) – Raises `ValueError` to refuse a URL; see
    [`require_http_url()`](#yb.download.bounded.require_http_url). Applied to every URL yt-dlp requests. Not
    an egress sandbox: redirects are followed by the HTTP layer, so only
    where a chain ends is checked (its content is then refused; the hops
    in between are requested blind), and the check sees a URL, not the
    address its host resolves to.
  * **extra_opts** ([`Mapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Deployment yt-dlp options, restricted to
    [`DEPLOYMENT_OPT_KEYS`](#yb.download.bounded.DEPLOYMENT_OPT_KEYS) (credentials, cookies, proxy); anything
    else raises, so no option can widen a cap or redirect the output.
  * **cookies_file** ([`Union`](https://docs.python.org/3/library/typing.html#typing.Union)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path), [`Literal`](https://docs.python.org/3/library/typing.html#typing.Literal)[[`False`](https://docs.python.org/3/builtins/constants.html#False)], [`None`](https://docs.python.org/3/builtins/constants.html#None)]) – As in [`download_youtube_video()`](yb.download.html.md#yb.download.download_youtube_video), except
    the default is `False`: a service fetching for remote users must
    not do it with the operator’s account by accident. Pass a path (or
    `None` for yb’s default file) to opt in.
  * **notice** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Copyright notice returned in the result.
* **Raises:**
  * [**ImportError**](https://docs.python.org/3/builtins/exceptions.html#ImportError) – yt-dlp is not installed (with the install command), raised
        before any network.
  * [**AudioTargetError**](#yb.download.bounded.AudioTargetError) – `validate_target` refused a URL (a `ValueError`).
  * [**ValueError**](https://docs.python.org/3/builtins/exceptions.html#ValueError) – A cap is not positive, or `extra_opts` has a key outside
        [`DEPLOYMENT_OPT_KEYS`](#yb.download.bounded.DEPLOYMENT_OPT_KEYS).
  * [**AudioLimitError**](#yb.download.bounded.AudioLimitError) – Playlist, live stream, too long, too large, or too slow.
  * [**AudioSourceError**](#yb.download.bounded.AudioSourceError) – yt-dlp could not get audio from the link.
  * [**RateLimitedError**](yb.download.html.md#yb.download.RateLimitedError) – The source is rate-limiting or bot-checking this
        client (a `RuntimeError`: retry later, the link may be fine).
* **Return type:**
  [`AudioDownload`](#yb.download.bounded.AudioDownload)

### yb.download.bounded.require_http_url(url)

Default target check: an http(s) URL with a host.

This is only the floor. A service fetching on behalf of untrusted callers
should pass a `validate_target` that also refuses loopback, private,
link-local and cloud-metadata hosts.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

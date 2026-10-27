# yb.download.bounded

Link-to-audio with the safety policy applied once: [`download_audio_bounded()`](#yb.download.bounded.download_audio_bounded).

A service that turns a user-supplied link into an audio file (an MCP tool, an
ingest endpoint) needs the same guard rails every time: refuse bad targets before
touching the network, refuse over-long sources before fetching a byte, cap the
download size, always produce mp3, and carry a copyright notice with the file.
That policy lives here so a second consumer does not copy it.

The caps are keyword-only arguments, and they are written *after* any caller
`extra_opts`, so a configured yt-dlp option (credentials, cookies, proxies)
can never widen them.

```pycon
>>> from yb.download import download_audio_bounded
>>> got = download_audio_bounded(url, max_bytes=60 * 2**20, max_duration_s=45 * 60)
>>> got.path, got.title, got.duration_s, got.notice
```

### Module Attributes

| [`DEFAULT_MAX_BYTES`](#yb.download.bounded.DEFAULT_MAX_BYTES)      | Default byte cap.                                                                            |
|-------------------------------------------------------------------------|----------------------------------------------------------------------------------------------|
| [`DEFAULT_MAX_DURATION_S`](#yb.download.bounded.DEFAULT_MAX_DURATION_S) | Default duration cap, in seconds (refuses livestream-length and multi-hour sources).         |
| [`AUDIO_CODEC`](#yb.download.bounded.AUDIO_CODEC)            | Output codec and quality handed to yt-dlp's audio extractor.                                 |
| [`COPYRIGHT_NOTICE`](#yb.download.bounded.COPYRIGHT_NOTICE)       | Travels with every download (store it next to the file).                                     |
| [`DEPLOYMENT_OPT_KEYS`](#yb.download.bounded.DEPLOYMENT_OPT_KEYS)    | how to reach and authenticate to the source, nothing about what is fetched or where it goes. |
| [`TargetValidator`](#yb.download.bounded.TargetValidator)        | raises `ValueError` to refuse `url`.                                                         |

### Functions

| [`download_audio_bounded`](#yb.download.bounded.download_audio_bounded)(url, \*, download_dir)   | Download the audio of one video link as mp3, refusing what exceeds the caps.   |
|--------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| [`require_http_url`](#yb.download.bounded.require_http_url)(url)                           | Default target check: an http(s) URL with a host.                              |

### Classes

| [`AudioDownload`](#yb.download.bounded.AudioDownload)(path, title, duration_s, ...)   | A bounded audio download.   |
|------------------------------------------------------------------------------------------------|-----------------------------|

### Exceptions

| [`AudioLimitError`](#yb.download.bounded.AudioLimitError)   | The source exceeds a cap (duration or size); nothing is left on disk.   |
|--------------------------------------------------------------------|-------------------------------------------------------------------------|

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

The source exceeds a cap (duration or size); nothing is left on disk.

### yb.download.bounded.COPYRIGHT_NOTICE *= "Downloaded from a user-supplied link — respect the source's copyright and terms of service; you are responsible for having the right to use it."*

Travels with every download (store it next to the file).

### yb.download.bounded.DEFAULT_MAX_BYTES *= 83886080*

Default byte cap. Above the mp3 size of a source at the default duration cap
(45 min at 192 kbps is about 65 MB), so a source that passes one passes both.

### yb.download.bounded.DEFAULT_MAX_DURATION_S *= 2700*

Default duration cap, in seconds (refuses livestream-length and multi-hour sources).

### yb.download.bounded.DEPLOYMENT_OPT_KEYS *= frozenset({'cookiefile', 'cookiesfrombrowser', 'extractor_args', 'http_headers', 'js_runtimes', 'password', 'proxy', 'remote_components', 'source_address', 'username'})*

how to reach and
authenticate to the source, nothing about what is fetched or where it goes.

* **Type:**
  yt-dlp options a deployment may pass in `extra_opts`

### yb.download.bounded.TargetValidator

raises `ValueError` to refuse `url`.

* **Type:**
  A target check

alias of [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`None`](https://docs.python.org/3/builtins/constants.html#None)]

### yb.download.bounded.download_audio_bounded(url, \*, download_dir, max_bytes=83886080, max_duration_s=2700, validate_target=<function require_http_url>, extra_opts=None, cookies_file=None, notice="Downloaded from a user-supplied link — respect the source's copyright and terms of service; you are responsible for having the right to use it.")

Download the audio of one video link as mp3, refusing what exceeds the caps.

Order: `validate_target` on `url` (before any network), a metadata-only
fetch that refuses playlists, live streams and over-long sources (before any
media bytes) and re-validates the resolved page URL, then the download with
the caps pinned, then a size check on the extracted file. The mp3 is written
to a fresh private directory under `download_dir` (so concurrent calls never
collide); on any failure that directory is removed.

* **Parameters:**
  * **url** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – A page link (YouTube, SoundCloud, Bandcamp, …).
  * **download_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – Parent of the per-call directory holding the mp3 (the caller
    owns that directory from then on and removes it after ingest).
  * **max_bytes** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – Cap on the downloaded and on the extracted file.
  * **max_duration_s** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – Cap on the source’s duration. A source that reports no
    duration passes this check and is bounded by `max_bytes` alone.
  * **validate_target** ([`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`None`](https://docs.python.org/3/builtins/constants.html#None)]) – Raises `ValueError` to refuse a URL; see
    [`require_http_url()`](#yb.download.bounded.require_http_url). Not an egress sandbox: yt-dlp follows
    redirects itself.
  * **extra_opts** ([`Mapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Deployment yt-dlp options, restricted to
    [`DEPLOYMENT_OPT_KEYS`](#yb.download.bounded.DEPLOYMENT_OPT_KEYS) (credentials, cookies, proxy); anything
    else raises, so no option can widen a cap or redirect the output.
  * **cookies_file** ([`Union`](https://docs.python.org/3/library/typing.html#typing.Union)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path), [`Literal`](https://docs.python.org/3/library/typing.html#typing.Literal)[[`False`](https://docs.python.org/3/builtins/constants.html#False)], [`None`](https://docs.python.org/3/builtins/constants.html#None)]) – As in [`download_youtube_video()`](yb.download.html.md#yb.download.download_youtube_video).
  * **notice** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Copyright notice returned in the result.
* **Raises:**
  * [**ValueError**](https://docs.python.org/3/builtins/exceptions.html#ValueError) – `validate_target` refused a URL, a cap is not positive, or
        `extra_opts` has a key outside [`DEPLOYMENT_OPT_KEYS`](#yb.download.bounded.DEPLOYMENT_OPT_KEYS).
  * [**AudioLimitError**](#yb.download.bounded.AudioLimitError) – Playlist, live stream, too long, or too large.
* **Return type:**
  [`AudioDownload`](#yb.download.bounded.AudioDownload)

### yb.download.bounded.require_http_url(url)

Default target check: an http(s) URL with a host.

This is only the floor. A service fetching on behalf of untrusted callers
should pass a `validate_target` that also refuses loopback, private,
link-local and cloud-metadata hosts.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

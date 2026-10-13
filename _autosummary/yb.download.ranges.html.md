# yb.download.ranges

Download just a time range of a video: parse start/end, build yt-dlp’s options.

Sourcing a sound effect or a clip from a long video should not mean downloading
the whole thing. `start=` / `end=` on [`yb.download.download_youtube_video()`](yb.download.html.md#yb.download.download_youtube_video)
and [`yb.download.download_youtube_audio()`](yb.download.html.md#yb.download.download_youtube_audio) take seconds (`7.9`) or
timestamps (`"0:07.9"`, `"1:02:03"`); this module turns them into
yt-dlp’s `download_ranges` option.

```pycon
>>> parse_timestamp("1:02.5")
62.5
>>> TimeRange.of(start="0:07.9", end=8.75).label
'7.9-8.75'
>>> TimeRange.of(start=30).label
'30-end'
```

yt-dlp cuts a range by handing the stream to **ffmpeg**, so the range path
needs ffmpeg on `PATH` (or `extra_opts={"ffmpeg_location": ...}`). Cuts land
on keyframes unless `precise_cuts=True` (re-encodes, slower, frame-accurate).
When the system ffmpeg is a build that lacks what yt-dlp asks of it, point
`ffmpeg_location` at another one (moviepy’s bundled ffmpeg, for example).

### Module Attributes

| [`Timestamp`](#yb.download.ranges.Timestamp)             | seconds, or a `[[h:]m:]s[.fraction]` string.                                   |
|------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| [`DOWNLOAD_RANGES_OPT`](#yb.download.ranges.DOWNLOAD_RANGES_OPT)   | yt-dlp option names this module sets.                                          |
| [`INFO_RANGE_KEY`](#yb.download.ranges.INFO_RANGE_KEY)        | Key under which a ranged download's span is recorded on `DownloadResult.info`. |
| [`MAX_TIMESTAMP_SECONDS`](#yb.download.ranges.MAX_TIMESTAMP_SECONDS) | beyond it a typo, not a video.                                                 |

### Functions

| [`default_range_func`](#yb.download.ranges.default_range_func)()                               | yt-dlp's `download_range_func` (imported lazily: yt-dlp is optional).      |
|-----------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------|
| [`parse_timestamp`](#yb.download.ranges.parse_timestamp)(value)                             | Seconds from a number or a `"[[h:]m:]s[.fraction]"` string.                |
| [`range_opts`](#yb.download.ranges.range_opts)(time_range, \*[, precise_cuts, ...])    | The yt-dlp options that download only `time_range`.                        |
| [`ranged_filename_template`](#yb.download.ranges.ranged_filename_template)(template, time_range, \*) | `template` with the range before the extension: `"T (id) [7.9-8.75].mp4"`. |

### Classes

| [`TimeRange`](#yb.download.ranges.TimeRange)([start, end])   | A span of a video, in seconds.   |
|----------------------------------------------------------------------------|----------------------------------|

### yb.download.ranges.DOWNLOAD_RANGES_OPT *= 'download_ranges'*

yt-dlp option names this module sets.

### yb.download.ranges.INFO_RANGE_KEY *= 'download_range'*

Key under which a ranged download’s span is recorded on `DownloadResult.info`.

### yb.download.ranges.MAX_TIMESTAMP_SECONDS *= 864000*

beyond it a typo, not a video.

* **Type:**
  Longest timestamp accepted (10 days)

### *class* yb.download.ranges.TimeRange(start=0.0, end=None)

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
  [`TimeRange`](#yb.download.ranges.TimeRange) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### yb.download.ranges.Timestamp *= int | float | str*

seconds, or a `[[h:]m:]s[.fraction]` string.

* **Type:**
  A time as callers give it

### yb.download.ranges.default_range_func()

yt-dlp’s `download_range_func` (imported lazily: yt-dlp is optional).

* **Return type:**
  [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### yb.download.ranges.parse_timestamp(value)

Seconds from a number or a `"[[h:]m:]s[.fraction]"` string.

* **Raises:**
  [**ValueError**](https://docs.python.org/3/builtins/exceptions.html#ValueError) – If `value` is negative, not finite, or not a timestamp.
* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### yb.download.ranges.range_opts(time_range, , precise_cuts=False, range_func=None)

The yt-dlp options that download only `time_range`.

* **Parameters:**
  * **time_range** ([`TimeRange`](#yb.download.ranges.TimeRange)) – The span to fetch.
  * **precise_cuts** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Re-encode at the cuts for frame-accurate bounds (slower).
  * **range_func** ([`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Stand-in for yt-dlp’s `download_range_func` (tests).
* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### yb.download.ranges.ranged_filename_template(template, time_range, , precise_cuts=False)

`template` with the range before the extension: `"T (id) [7.9-8.75].mp4"`.

Without it a clip would share the full video’s filename, and yt-dlp would
take one for the other (“already downloaded”). A precise cut is named
apart from a keyframe cut for the same reason. Only templates ending in
`.%(ext)s` (the default does) are changed; one written by hand is the
caller’s to keep distinct.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

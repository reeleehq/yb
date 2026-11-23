# yb.download.storyboards

YouTube storyboards: a video’s seek-bar thumbnails, by time, with no video download.

YouTube serves every video’s *storyboard*: sprite sheets of small frames
(`sb0` is 320x180, about one frame every 2 to 10 seconds) that the player
shows when you hover the seek bar. They are cheap to fetch (a few JPEGs per
video, no video stream, and they still load where video downloads hit a bot
wall), and they are enough to find *where* in a video something is: a scene,
a set, a drawn object. Text-to-frame search over a channel is built on them
(`illustration.frames`).

```pycon
>>> from yb.download import youtube_storyboard
>>> board = youtube_storyboard("https://youtu.be/dQw4w9WgXcQ")
>>> for t, image in board.frames():
...     ...  # t in seconds, image a PIL image (needs pillow)
```

Two limits to design for: a frame stands for a stretch of a few seconds (its
time is the start of that stretch, and can lag the moment shown by about a
second, so grab a few candidates around a hit when you cut the real frame with
[`download_youtube_video()`](yb.download.html.md#yb.download.download_youtube_video)’s `start`/`end`); and 320x180
finds scenes, not small props.

The frames are the video owner’s: a storyboard carries the video’s licence
(`Storyboard.license`, YouTube’s `"Creative Commons Attribution license
(reuse allowed)"` or nothing, which means the standard YouTube licence: all
rights reserved).

### Module Attributes

| [`DFLT_STORYBOARD_FORMAT`](#yb.download.storyboards.DFLT_STORYBOARD_FORMAT)   | The largest storyboard YouTube serves (320x180 frames).   |
|---------------------------------------------------------------------------|-----------------------------------------------------------|

### Functions

| [`youtube_storyboard`](#yb.download.storyboards.youtube_storyboard)(url, \*[, format_id, ...])   | Fetch a video's storyboard (metadata plus its sprite sheets; no video).   |
|--------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------|
| [`storyboard_formats`](#yb.download.storyboards.storyboard_formats)(info)                        | The storyboard formats in a yt-dlp info dict, largest first.              |

### Classes

| [`Storyboard`](#yb.download.storyboards.Storyboard)(video_id, url, title, duration, ...)   | A video's storyboard: its sheets, their tiling, and the video's identity and licence.   |
|----------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------|
| [`StoryboardSheet`](#yb.download.storyboards.StoryboardSheet)(start, duration, image_bytes)     | One sprite sheet: `rows` x `columns` frames covering `duration` s from `start`.         |

### yb.download.storyboards.DFLT_STORYBOARD_FORMAT *= 'sb0'*

The largest storyboard YouTube serves (320x180 frames). `sb1` .. `sb3` are
smaller (160x90 down to 48x27).

### *class* yb.download.storyboards.Storyboard(video_id, url, title, duration, license, format_id, width, height, rows, columns, sheets=())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A video’s storyboard: its sheets, their tiling, and the video’s identity and licence.

#### frame_times()

The start time of every frame, in order (what [`frames()`](#yb.download.storyboards.Storyboard.frames) yields).

```pycon
>>> sheet = StoryboardSheet(start=0.0, duration=8.0, image_bytes=b"")
>>> board = Storyboard("v", "u", None, 10.0, None, "sb0", 4, 2, 2, 2,
...                    sheets=(sheet, StoryboardSheet(8.0, 8.0, b"")))
>>> board.frame_times()
[0.0, 2.0, 4.0, 6.0, 8.0]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`float`](https://docs.python.org/3/builtins/functions.html#float)]

#### frames()

`(t, image)` for every frame: `t` in seconds, `image` a PIL image.

Needs `pillow`. Tiles past the video’s end (a last sheet’s padding) are
skipped.

* **Return type:**
  [`Iterator`](https://docs.python.org/3/library/typing.html#typing.Iterator)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

### *class* yb.download.storyboards.StoryboardSheet(start, duration, image_bytes)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One sprite sheet: `rows` x `columns` frames covering `duration` s from `start`.

### yb.download.storyboards.storyboard_formats(info)

The storyboard formats in a yt-dlp info dict, largest first.

```pycon
>>> storyboard_formats({"formats": [{"format_id": "18"},
...     {"format_id": "sb1", "format_note": "storyboard", "width": 160},
...     {"format_id": "sb0", "format_note": "storyboard", "width": 320}]})
[{'format_id': 'sb0', 'format_note': 'storyboard', 'width': 320}, {'format_id': 'sb1', 'format_note': 'storyboard', 'width': 160}]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]

### yb.download.storyboards.youtube_storyboard(url, , format_id='sb0', extra_opts=None, cookies_file=None, ydl_cls=None)

Fetch a video’s storyboard (metadata plus its sprite sheets; no video).

* **Parameters:**
  * **url** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The video’s URL (or anything yt-dlp resolves to one video).
  * **format_id** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Which storyboard: `sb0` (default, 320x180) down to `sb3`.
  * **extra_opts** ([`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Raw yt-dlp options, as everywhere in [`yb.download`](yb.download.html.md#module-yb.download).
  * **cookies_file** ([`Any`](https://docs.python.org/3/library/typing.html#typing.Any)) – As in [`download_youtube_video()`](yb.download.html.md#yb.download.download_youtube_video).
  * **ydl_cls** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)[[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)], [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]) – What to build instead of `yt_dlp.YoutubeDL` (a fake in tests).
* **Raises:**
  [**LookupError**](https://docs.python.org/3/builtins/exceptions.html#LookupError) – The video has no storyboard of that format (live streams,
      some very short videos); the message lists the ones it has.
* **Return type:**
  [`Storyboard`](#yb.download.storyboards.Storyboard)

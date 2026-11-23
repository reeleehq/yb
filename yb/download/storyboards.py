"""YouTube storyboards: a video's seek-bar thumbnails, by time, with no video download.

YouTube serves every video's *storyboard*: sprite sheets of small frames
(``sb0`` is 320x180, about one frame every 2 to 10 seconds) that the player
shows when you hover the seek bar. They are cheap to fetch (a few JPEGs per
video, no video stream, and they still load where video downloads hit a bot
wall), and they are enough to find *where* in a video something is: a scene,
a set, a drawn object. Text-to-frame search over a channel is built on them
(``illustration.frames``).

    >>> from yb.download import youtube_storyboard  # doctest: +SKIP
    >>> board = youtube_storyboard("https://youtu.be/dQw4w9WgXcQ")  # doctest: +SKIP
    >>> for t, image in board.frames():  # doctest: +SKIP
    ...     ...  # t in seconds, image a PIL image (needs pillow)

Two limits to design for: a frame stands for a stretch of a few seconds (its
time is the start of that stretch, and can lag the moment shown by about a
second, so grab a few candidates around a hit when you cut the real frame with
:func:`~yb.download.download_youtube_video`'s ``start``/``end``); and 320x180
finds scenes, not small props.

The frames are the video owner's: a storyboard carries the video's licence
(``Storyboard.license``, YouTube's ``"Creative Commons Attribution license
(reuse allowed)"`` or nothing, which means the standard YouTube licence: all
rights reserved).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

__all__ = [
    "Storyboard",
    "StoryboardSheet",
    "youtube_storyboard",
    "storyboard_formats",
    "DFLT_STORYBOARD_FORMAT",
]

#: The largest storyboard YouTube serves (320x180 frames). ``sb1`` .. ``sb3`` are
#: smaller (160x90 down to 48x27).
DFLT_STORYBOARD_FORMAT = "sb0"


@dataclass(frozen=True)
class StoryboardSheet:
    """One sprite sheet: ``rows`` x ``columns`` frames covering ``duration`` s from ``start``."""

    start: float
    duration: float
    image_bytes: bytes


@dataclass(frozen=True)
class Storyboard:
    """A video's storyboard: its sheets, their tiling, and the video's identity and licence."""

    video_id: str
    url: str
    title: str | None
    duration: float | None
    license: str | None
    format_id: str
    width: int
    height: int
    rows: int
    columns: int
    sheets: tuple[StoryboardSheet, ...] = field(default=())

    def frame_times(self) -> list[float]:
        """The start time of every frame, in order (what :meth:`frames` yields).

        >>> sheet = StoryboardSheet(start=0.0, duration=8.0, image_bytes=b"")
        >>> board = Storyboard("v", "u", None, 10.0, None, "sb0", 4, 2, 2, 2,
        ...                    sheets=(sheet, StoryboardSheet(8.0, 8.0, b"")))
        >>> board.frame_times()
        [0.0, 2.0, 4.0, 6.0, 8.0]
        """
        return [t for _, t, _, _ in self._tiles()]

    def frames(self) -> Iterator[tuple[float, Any]]:
        """``(t, image)`` for every frame: ``t`` in seconds, ``image`` a PIL image.

        Needs ``pillow``. Tiles past the video's end (a last sheet's padding) are
        skipped.
        """
        try:
            from PIL import Image
        except ImportError as exc:  # pragma: no cover - the message is the point
            raise ImportError(
                "storyboard frames are PIL images: install pillow"
            ) from exc
        import io

        opened: dict[int, Any] = {}
        for index, t, row, col in self._tiles():
            if index not in opened:
                opened = {index: Image.open(io.BytesIO(self.sheets[index].image_bytes))}
            box = (
                col * self.width,
                row * self.height,
                (col + 1) * self.width,
                (row + 1) * self.height,
            )
            yield t, opened[index].crop(box)

    def _tiles(self) -> Iterator[tuple[int, float, int, int]]:
        per_sheet = self.rows * self.columns
        end = self.duration
        for index, sheet in enumerate(self.sheets):
            step = sheet.duration / per_sheet
            for k in range(per_sheet):
                t = sheet.start + k * step
                if end is not None and t >= end:
                    return
                yield index, t, divmod(k, self.columns)[0], k % self.columns


def storyboard_formats(info: dict) -> list[dict]:
    """The storyboard formats in a yt-dlp info dict, largest first.

    >>> storyboard_formats({"formats": [{"format_id": "18"},
    ...     {"format_id": "sb1", "format_note": "storyboard", "width": 160},
    ...     {"format_id": "sb0", "format_note": "storyboard", "width": 320}]})
    [{'format_id': 'sb0', 'format_note': 'storyboard', 'width': 320}, {'format_id': 'sb1', 'format_note': 'storyboard', 'width': 160}]
    """
    found = [
        f
        for f in info.get("formats") or ()
        if f.get("format_note") == "storyboard" or str(f.get("format_id", "")).startswith("sb")
    ]
    return sorted(found, key=lambda f: -(f.get("width") or 0))


def youtube_storyboard(
    url: str,
    *,
    format_id: str = DFLT_STORYBOARD_FORMAT,
    extra_opts: dict | None = None,
    cookies_file: Any = None,
    ydl_cls: Callable[[dict], Any] | None = None,
) -> Storyboard:
    """Fetch a video's storyboard (metadata plus its sprite sheets; no video).

    Args:
        url: The video's URL (or anything yt-dlp resolves to one video).
        format_id: Which storyboard: ``sb0`` (default, 320x180) down to ``sb3``.
        extra_opts: Raw yt-dlp options, as everywhere in :mod:`yb.download`.
        cookies_file: As in :func:`~yb.download.download_youtube_video`.
        ydl_cls: What to build instead of ``yt_dlp.YoutubeDL`` (a fake in tests).

    Raises:
        LookupError: The video has no storyboard of that format (live streams,
            some very short videos); the message lists the ones it has.
    """
    from yb.download.youtube import youtube_dl

    base = {"quiet": True, "skip_download": True, "noplaylist": True}
    with youtube_dl(
        base, extra_opts=extra_opts, cookies_file=cookies_file, ydl_cls=ydl_cls
    ) as ydl:
        info = ydl.extract_info(url, download=False) or {}
        formats = {f.get("format_id"): f for f in storyboard_formats(info)}
        fmt = formats.get(format_id)
        if fmt is None:
            raise LookupError(
                f"{url}: no storyboard {format_id!r} (has: {sorted(formats) or 'none'})"
            )
        sheets, start = [], 0.0
        for fragment in fmt.get("fragments") or ():
            frag_url = fragment.get("url") or (
                (fmt.get("fragment_base_url") or "") + (fragment.get("path") or "")
            )
            duration = float(fragment.get("duration") or 0.0)
            with ydl.urlopen(frag_url) as response:
                data = response.read()
            sheets.append(StoryboardSheet(start=start, duration=duration, image_bytes=data))
            start += duration
    duration = info.get("duration")
    return Storyboard(
        video_id=str(info.get("id") or ""),
        url=info.get("webpage_url") or url,
        title=info.get("title"),
        duration=None if duration is None else float(duration),
        license=info.get("license"),
        format_id=format_id,
        width=int(fmt["width"]),
        height=int(fmt["height"]),
        rows=int(fmt["rows"]),
        columns=int(fmt["columns"]),
        sheets=tuple(sheets),
    )

"""Download just a time range of a video: parse start/end, build yt-dlp's options.

Sourcing a sound effect or a clip from a long video should not mean downloading
the whole thing. ``start=`` / ``end=`` on :func:`yb.download.download_youtube_video`
and :func:`yb.download.download_youtube_audio` take seconds (``7.9``) or
timestamps (``"0:07.9"``, ``"1:02:03"``); this module turns them into
yt-dlp's ``download_ranges`` option.

    >>> parse_timestamp("1:02.5")
    62.5
    >>> TimeRange.of(start="0:07.9", end=8.75).label
    '7.9-8.75'
    >>> TimeRange.of(start=30).label
    '30-end'

yt-dlp cuts a range by handing the stream to **ffmpeg**, so the range path
needs ffmpeg on ``PATH`` (or ``extra_opts={"ffmpeg_location": ...}``). Cuts land
on keyframes unless ``precise_cuts=True`` (re-encodes, slower, frame-accurate).
When the system ffmpeg is a build that lacks what yt-dlp asks of it, point
``ffmpeg_location`` at another one (moviepy's bundled ffmpeg, for example).
"""

from __future__ import annotations

import math
import numbers
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

#: A time as callers give it: seconds, or a ``[[h:]m:]s[.fraction]`` string.
Timestamp = int | float | str

#: yt-dlp option names this module sets.
DOWNLOAD_RANGES_OPT = "download_ranges"
FORCE_KEYFRAMES_OPT = "force_keyframes_at_cuts"

#: Key under which a ranged download's span is recorded on ``DownloadResult.info``.
INFO_RANGE_KEY = "download_range"

#: Longest timestamp accepted (10 days): beyond it a typo, not a video.
MAX_TIMESTAMP_SECONDS = 10 * 24 * 3600

_CLOCK_RE = re.compile(r"^(?:(?:(\d+):)?(\d+):)?(\d+(?:\.\d+)?)$")
_CLOCK_MAX_PARTS = 3


def parse_timestamp(value: Timestamp) -> float:
    """Seconds from a number or a ``"[[h:]m:]s[.fraction]"`` string.

    Raises:
        ValueError: If ``value`` is negative, not finite, or not a timestamp.
    """
    if isinstance(value, bool):
        raise ValueError(f"not a timestamp: {value!r}")
    if isinstance(value, numbers.Real):
        try:
            seconds = float(value)
        except OverflowError:
            raise ValueError(f"timestamp too large: {value!r}") from None
    elif isinstance(value, str):
        text = value.strip()
        # "90", "1:30", "1:02:03.5"; minutes/seconds aren't capped at 59 (yt-dlp
        # accepts "90:00"), but a bare negative or garbage is an error.
        match = _CLOCK_RE.match(text)
        if not match:
            raise ValueError(
                f"not a timestamp: {value!r} (use seconds, 'mm:ss' or 'hh:mm:ss')"
            )
        hours, minutes, secs = match.groups()
        try:
            seconds = int(hours or 0) * 3600 + int(minutes or 0) * 60 + float(secs)
        except OverflowError:
            raise ValueError(f"timestamp too large: {value!r}") from None
    else:
        raise ValueError(f"not a timestamp: {value!r}")
    if not math.isfinite(seconds) or not 0 <= seconds <= MAX_TIMESTAMP_SECONDS:
        raise ValueError(
            f"a timestamp must be between 0 and {MAX_TIMESTAMP_SECONDS}s, "
            f"got {value!r}"
        )
    return seconds + 0.0  # turns -0.0 into 0.0


def _fmt_seconds(seconds: float) -> str:
    return f"{seconds:.3f}".rstrip("0").rstrip(".")


@dataclass(frozen=True)
class TimeRange:
    """A span of a video, in seconds. ``end=None`` means "to the end"."""

    start: float = 0.0
    end: float | None = None

    @classmethod
    def of(
        cls, *, start: Timestamp | None = None, end: Timestamp | None = None
    ) -> "TimeRange | None":
        """Build from user input; ``None`` when neither bound is given.

        Raises:
            ValueError: On a bad timestamp, or ``end`` not after ``start``.
        """
        if start is None and end is None:
            return None
        lo = 0.0 if start is None else parse_timestamp(start)
        hi = None if end is None else parse_timestamp(end)
        if hi is not None and hi <= lo:
            raise ValueError(
                f"end ({_fmt_seconds(hi)}s) must be after start ({_fmt_seconds(lo)}s)"
            )
        return cls(lo, hi)

    @property
    def label(self) -> str:
        """Compact, filename-safe form: ``"7.9-8.75"`` or ``"30-end"``."""
        end = "end" if self.end is None else _fmt_seconds(self.end)
        return f"{_fmt_seconds(self.start)}-{end}"

    def as_info(self) -> dict[str, float | None]:
        """The span as recorded on a result's ``info`` (for provenance)."""
        return {"start": self.start, "end": self.end}


def default_range_func() -> Callable[..., Any]:
    """yt-dlp's ``download_range_func`` (imported lazily: yt-dlp is optional)."""
    from yt_dlp.utils import download_range_func

    return download_range_func


def range_opts(
    time_range: TimeRange,
    *,
    precise_cuts: bool = False,
    range_func: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """The yt-dlp options that download only ``time_range``.

    Args:
        time_range: The span to fetch.
        precise_cuts: Re-encode at the cuts for frame-accurate bounds (slower).
        range_func: Stand-in for yt-dlp's ``download_range_func`` (tests).
    """
    make = range_func or default_range_func()
    end = math.inf if time_range.end is None else time_range.end
    opts: dict[str, Any] = {
        DOWNLOAD_RANGES_OPT: make(None, [(time_range.start, end)]),
    }
    if precise_cuts:
        opts[FORCE_KEYFRAMES_OPT] = True
    return opts


def ranged_filename_template(
    template: str, time_range: TimeRange, *, precise_cuts: bool = False
) -> str:
    """``template`` with the range before the extension: ``"T (id) [7.9-8.75].mp4"``.

    Without it a clip would share the full video's filename, and yt-dlp would
    take one for the other ("already downloaded"). A precise cut is named
    apart from a keyframe cut for the same reason. Only templates ending in
    ``.%(ext)s`` (the default does) are changed; one written by hand is the
    caller's to keep distinct.
    """
    tail = ".%(ext)s"
    if not template.endswith(tail):
        return template
    label = f"{time_range.label} precise" if precise_cuts else time_range.label
    return f"{template[: -len(tail)]} [{label}]{tail}"

"""Polite pacing for yt-dlp downloads, and a useful message when YouTube pushes back.

``pace="polite"`` (or a :class:`Pace`) maps to yt-dlp's sleep and rate-limit
options, so a long playlist can be fetched without hammering YouTube. The
default everywhere is ``pace=None``: no options are added and behaviour is
unchanged. A raw yt-dlp option in ``extra_opts`` still wins over a pace.

    >>> pace_opts("polite")["sleep_interval"]
    20
    >>> pace_opts(None)
    {}
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True)
class Pace:
    """How gently to talk to YouTube.

    Attributes:
        sleep_interval: Seconds to sleep before each download (yt-dlp
            ``sleep_interval``); with ``max_sleep_interval`` a random value in
            between is used.
        max_sleep_interval: Upper bound of the random sleep.
        sleep_requests: Seconds to sleep between metadata requests
            (yt-dlp ``sleep_interval_requests``).
        limit_rate: Maximum download rate, e.g. ``"4M"`` or ``"500K"`` (bytes/s).
    """

    sleep_interval: float | None = None
    max_sleep_interval: float | None = None
    sleep_requests: float | None = None
    limit_rate: str | None = None


#: Named paces accepted wherever ``pace=`` is.
PACE_PRESETS: dict[str, Pace] = {
    "polite": Pace(
        sleep_interval=20, max_sleep_interval=60, sleep_requests=1, limit_rate="4M"
    ),
}

_RATE_UNITS = {"": 1, "K": 1024, "M": 1024**2, "G": 1024**3}


def parse_rate(rate: str | int | float) -> int:
    """Parse a rate such as ``"4M"`` or ``"500k"`` into bytes per second.

    >>> parse_rate("4M")
    4194304
    """
    if isinstance(rate, (int, float)):
        return int(rate)
    m = re.fullmatch(r"\s*([\d.]+)\s*([KMGkmg]?)[Bb]?\s*", rate)
    if not m:
        raise ValueError(f"Cannot parse rate {rate!r}; use e.g. '4M' or '500K'")
    return int(float(m.group(1)) * _RATE_UNITS[m.group(2).upper()])


def resolve_pace(pace: Pace | str | None) -> Pace | None:
    """Turn a preset name, a :class:`Pace` or ``None`` into a ``Pace`` (or ``None``)."""
    if pace is None or isinstance(pace, Pace):
        return pace
    try:
        return PACE_PRESETS[pace]
    except KeyError:
        raise ValueError(
            f"Unknown pace {pace!r}; use a Pace or one of {sorted(PACE_PRESETS)}"
        ) from None


def pace_opts(pace: Pace | str | None) -> dict:
    """The yt-dlp options for ``pace`` (empty for ``None``)."""
    p = resolve_pace(pace)
    if p is None:
        return {}
    opts: dict = {}
    if p.sleep_interval is not None:
        opts["sleep_interval"] = p.sleep_interval
    if p.max_sleep_interval is not None:
        opts["max_sleep_interval"] = p.max_sleep_interval
    if p.sleep_requests is not None:
        opts["sleep_interval_requests"] = p.sleep_requests
    if p.limit_rate is not None:
        opts["ratelimit"] = parse_rate(p.limit_rate)
    return opts


class RateLimitedError(RuntimeError):
    """YouTube refused the request (HTTP 429 or a "confirm you're not a bot" wall)."""


BACKOFF_HINT = (
    "YouTube is rate-limiting or bot-checking this client. Back off for a few "
    "hours (the block is per IP and often lifts on its own), then retry with "
    "pace='polite', a download_archive= so finished items are skipped, and "
    "cookies (cookies_file= or cookies_from_browser=). Fewer items per run "
    "(playlist_items='1-20') also helps."
)

_BLOCK_PATTERNS = re.compile(
    r"HTTP Error 429|Too Many Requests|confirm you.re not a bot|Sign in to confirm",
    re.IGNORECASE,
)


@contextmanager
def explain_rate_limit() -> Iterator[None]:
    """Re-raise yt-dlp errors that look like a block as :class:`RateLimitedError`."""
    try:
        yield
    except Exception as exc:
        if _BLOCK_PATTERNS.search(str(exc)):
            raise RateLimitedError(f"{BACKOFF_HINT}\nyt-dlp said: {exc}") from exc
        raise

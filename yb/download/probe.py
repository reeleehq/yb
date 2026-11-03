"""Online checks for servers: do the configured cookies still get past YouTube?

A cookies file exported from an everyday browser session goes stale: YouTube
rotates the session cookies as a security measure, after which every client gets
"Sign in to confirm you're not a bot". :func:`check_cookies` finds that out
with one metadata request for a known public video, instead of on the first real
download, and says how to re-export cookies that do not rotate. ``yb check
--online`` runs it.

    >>> from yb.download.probe import check_cookies
    >>> print("\\n".join(check_cookies()) or "cookies ok")  # doctest: +SKIP
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from yb.download.youtube import CookiesFile, default_cookies_file, youtube_video_info

#: A public video that has stayed up since 2005 ("Me at the zoo").
PROBE_VIDEO_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"

#: yt-dlp's wording when the cookies it was given stop authenticating.
ROTATED_MARKER = "cookies are no longer valid"

#: yt-dlp's wording for YouTube's bot wall.
BOT_WALL_MARKERS = ("confirm you're not a bot", "confirm you’re not a bot")

#: yt-dlp's guide to exporting YouTube cookies.
COOKIE_WIKI_URL = (
    "https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies"
)

#: How to export cookies the browser will not rotate.
COOKIE_EXPORT_STEPS = (
    "Export them again so the browser never rotates them: open a private / "
    "incognito window, log in to YouTube, go to https://www.youtube.com/robots.txt "
    "in that same tab, export the youtube.com cookies in Netscape format (a "
    "cookies.txt extension), then close the private window right away and never "
    f"reopen that session. See {COOKIE_WIKI_URL}"
)


class _WarningLog:
    """A yt-dlp ``logger`` that keeps warnings and errors, and prints nothing."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    def debug(self, msg: str) -> None:
        pass

    info = debug

    def warning(self, msg: str) -> None:
        self.messages.append(msg)

    error = warning


def _bot_walled(text: str) -> bool:
    return any(marker in text for marker in BOT_WALL_MARKERS)


def check_cookies(
    cookies_file: CookiesFile = None,
    *,
    probe_url: str = PROBE_VIDEO_URL,
    fetch_info: Callable[..., Any] = youtube_video_info,
) -> list[str]:
    """Problems with the cookies downloads would use (empty when they work).

    One metadata request for ``probe_url`` with ``cookies_file`` (``None``: the
    file downloads would use by default, see
    :func:`~yb.download.youtube.default_cookies_file`). With no file at all there
    is nothing to check and the result is empty.

    Args:
        cookies_file: As in :func:`~yb.download.download_youtube_video`.
        probe_url: A public video every working setup can read.
        fetch_info: Metadata fetcher (``youtube_video_info``; a fake in tests).

    Returns:
        Messages ending with the fix: the cookies were rotated or expired, the
        bot wall stopped them, or the probe failed for another reason.
    """
    path = default_cookies_file() if cookies_file is None else cookies_file
    if not path:
        return []
    log = _WarningLog()
    try:
        fetch_info(probe_url, cookies_file=Path(path), extra_opts={"logger": log})
    except Exception as exc:  # the probe reports, it never raises
        if _bot_walled(str(exc)):
            return [
                f"YouTube's bot check refused the cookies in {path}: they are "
                f"expired, rotated, or from a logged-out session. {COOKIE_EXPORT_STEPS}"
            ]
        return [f"Could not read {probe_url} with the cookies in {path}: {exc}"]
    if any(ROTATED_MARKER in m for m in log.messages):
        return [
            f"The cookies in {path} were rotated or expired (YouTube no longer "
            f"accepts them as logged in). {COOKIE_EXPORT_STEPS}"
        ]
    return []

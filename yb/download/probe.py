"""Online checks for servers: do the configured cookies still get past YouTube?

A cookies file exported from an everyday browser session goes stale: YouTube
rotates the session cookies as a security measure, after which every client gets
"Sign in to confirm you're not a bot". :func:`check_cookies` finds that out
before the first real download: it checks the file holds a logged-in session,
then reads one known public video with it, on a private copy so the check never
rewrites the file. :func:`check_po_token_server` pings the PO-token provider's
server. ``yb check --online`` runs both.

    >>> from yb.download.probe import check_cookies
    >>> print("\\n".join(check_cookies()) or "cookies ok")  # doctest: +SKIP
"""

from __future__ import annotations

import http.cookiejar
import os
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from yb.download.requirements import PO_TOKEN_SERVER_URL
from yb.download.youtube import (
    COOKIES_FILE_ENV,
    CookiesFile,
    default_cookies_file,
    youtube_dl,
)

#: A public video that has stayed up since 2005 ("Me at the zoo").
PROBE_VIDEO_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"

#: yt-dlp's wording when the cookies it was given stop authenticating.
ROTATED_MARKER = "cookies are no longer valid"

#: yt-dlp's wording for YouTube's bot wall.
BOT_WALL_MARKERS = ("confirm you're not a bot", "confirm you’re not a bot")

#: What makes a jar a logged-in YouTube session, by yt-dlp's own rule: the
#: login cookie plus one of the API session ids.
LOGIN_COOKIE = "LOGIN_INFO"
SESSION_ID_COOKIES = frozenset({"SAPISID", "__Secure-1PAPISID", "__Secure-3PAPISID"})
YOUTUBE_COOKIE_DOMAIN = "youtube.com"

#: Seconds to wait for the PO-token server's ``/ping``.
PING_TIMEOUT_S = 3

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


def configured_cookies(
    cookies_file: CookiesFile = None,
) -> tuple[Path | None, str | None]:
    """``(file, problem)``: the cookies file downloads would use, or why there is none.

    ``cookies_file`` as in :func:`~yb.download.download_youtube_video`. With
    ``None``, a ``$YB_COOKIES_FILE`` naming a missing file is a problem (downloads
    would silently go anonymous); no file configured at all is not.
    """
    if cookies_file is False:
        return None, None
    if cookies_file is not None:
        path = Path(cookies_file).expanduser()
        return (
            (path, None)
            if path.is_file()
            else (None, f"cookies file not found: {path}")
        )
    named = os.environ.get(COOKIES_FILE_ENV)
    if named and not Path(named).expanduser().is_file():
        return None, (
            f"${COOKIES_FILE_ENV} points to {named}, which does not exist, so "
            "downloads go without cookies."
        )
    return default_cookies_file(), None


def logged_in_problem(path: Path) -> str | None:
    """Why ``path`` is not a logged-in YouTube session (unexpired), or ``None``."""
    jar = http.cookiejar.MozillaCookieJar()
    try:
        jar.load(str(path))  # expired cookies are dropped
    except (http.cookiejar.LoadError, OSError) as exc:
        return f"cannot read {path} as a Netscape cookies file: {exc}"
    names = {
        c.name for c in jar if c.domain.lstrip(".").endswith(YOUTUBE_COOKIE_DOMAIN)
    }
    if LOGIN_COOKIE in names and names & SESSION_ID_COOKIES:
        return None
    return (
        f"{path} holds no logged-in YouTube session (no unexpired {LOGIN_COOKIE} "
        f"plus one of {sorted(SESSION_ID_COOKIES)}), so YouTube sees an anonymous "
        f"client. {COOKIE_EXPORT_STEPS}"
    )


def _probe_info(url: str, *, cookies_file: Path, extra_opts: dict) -> Any:
    """Metadata for ``url`` with the cookies on a private copy (never rewritten)."""
    opts = {"quiet": True, "skip_download": True, "noplaylist": True}
    with youtube_dl(
        opts, extra_opts=extra_opts, cookies_file=cookies_file, private_cookie_copy=True
    ) as ydl:
        return ydl.extract_info(url, download=False)


def _bot_walled(text: str) -> bool:
    return any(marker in text for marker in BOT_WALL_MARKERS)


def check_cookies(
    cookies_file: CookiesFile = None,
    *,
    probe_url: str = PROBE_VIDEO_URL,
    fetch_info: Callable[..., Any] = _probe_info,
) -> list[str]:
    """Problems with the cookies downloads would use (empty when they work).

    Checks that the file holds a logged-in session, then reads ``probe_url``
    with it (one metadata fetch; yt-dlp works on a copy, so the file is left as
    it was). With no file configured there is nothing to check.

    Args:
        cookies_file: As in :func:`~yb.download.download_youtube_video`.
        probe_url: A public video every working setup can read.
        fetch_info: ``(url, *, cookies_file, extra_opts)`` metadata fetcher; a
            fake in tests.

    Returns:
        Messages ending with the fix: no or a missing file where one was named,
        not a logged-in session, rotated or expired, refused by the bot check,
        or the probe failed for another reason.
    """
    path, problem = configured_cookies(cookies_file)
    if problem:
        return [problem]
    if path is None:
        return []
    if problem := logged_in_problem(path):
        return [problem]
    log = _WarningLog()
    try:
        fetch_info(probe_url, cookies_file=path, extra_opts={"logger": log})
    except Exception as exc:  # the probe reports, it never raises
        if _bot_walled(str(exc)):
            return [
                f"YouTube's bot check refused the client using {path}: the cookies "
                "are expired or rotated, or YouTube is challenging this IP whatever "
                f"the cookies. {COOKIE_EXPORT_STEPS}"
            ]
        return [f"Could not read {probe_url} with the cookies in {path}: {exc}"]
    if any(ROTATED_MARKER in m for m in log.messages):
        return [
            f"The cookies in {path} were rotated or expired (YouTube no longer "
            f"accepts them as logged in). {COOKIE_EXPORT_STEPS}"
        ]
    return []


def check_po_token_server(
    base_url: str = PO_TOKEN_SERVER_URL,
    *,
    urlopen: Callable[..., Any] = urllib.request.urlopen,
    timeout_s: float = PING_TIMEOUT_S,
) -> list[str]:
    """Problems reaching the PO-token provider's server (``GET <base_url>/ping``).

    The plugin alone does nothing: without its server, yt-dlp warns and carries
    on without tokens.
    """
    ping = f"{base_url.rstrip('/')}/ping"
    try:
        with urlopen(ping, timeout=timeout_s):
            return []
    except Exception as exc:  # reported, never raised
        return [
            f"The PO-token provider is installed but its server does not answer at "
            f"{ping} ({exc}). Start it, e.g. docker run -d -p 127.0.0.1:4416:4416 "
            "--init brainicism/bgutil-ytdlp-pot-provider"
        ]

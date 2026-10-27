"""Link-to-audio with the safety policy applied once: :func:`download_audio_bounded`.

A service that turns a user-supplied link into an audio file (an MCP tool, an
ingest endpoint) needs the same guard rails every time: refuse bad targets before
touching the network, refuse over-long sources before fetching a byte, cap the
download size, always produce mp3, and carry a copyright notice with the file.
That policy lives here so a second consumer does not copy it.

The caps are keyword-only arguments, and they are written *after* any caller
``extra_opts``, so a configured yt-dlp option (credentials, cookies, proxies)
can never widen them.

    >>> from yb.download import download_audio_bounded  # doctest: +SKIP
    >>> got = download_audio_bounded(url, max_bytes=60 * 2**20, max_duration_s=45 * 60)  # doctest: +SKIP
    >>> got.path, got.title, got.duration_s, got.notice  # doctest: +SKIP
"""

from __future__ import annotations

import urllib.parse
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from yb.download.youtube import (
    CookiesFile,
    PathLike,
    download_youtube_video,
    youtube_video_info,
)

#: Default byte cap (mp3 of a long track is tens of MB).
DEFAULT_MAX_BYTES = 60 * 1024 * 1024

#: Default duration cap, in seconds (refuses livestream-length and multi-hour sources).
DEFAULT_MAX_DURATION_S = 45 * 60

#: Output codec and quality handed to yt-dlp's audio extractor.
AUDIO_CODEC = "mp3"
AUDIO_QUALITY = "192"

#: Travels with every download (store it next to the file).
COPYRIGHT_NOTICE = (
    "Downloaded from a user-supplied link — respect the source's copyright and "
    "terms of service; you are responsible for having the right to use it."
)

_ALLOWED_SCHEMES = frozenset({"http", "https"})

#: A target check: raises ``ValueError`` to refuse ``url``.
TargetValidator = Callable[[str], None]


class AudioLimitError(ValueError):
    """The source exceeds a cap (duration or size); nothing is left on disk."""


def require_http_url(url: str) -> None:
    """Default target check: an http(s) URL with a host.

    This is only the floor. A service fetching on behalf of untrusted callers
    should pass a ``validate_target`` that also refuses loopback, private,
    link-local and cloud-metadata hosts.
    """
    parts = urllib.parse.urlparse(url)
    if parts.scheme not in _ALLOWED_SCHEMES:
        raise ValueError(f"only http/https URLs are supported, got {parts.scheme!r}")
    if not parts.hostname:
        raise ValueError(f"URL has no host: {url!r}")


@dataclass
class AudioDownload:
    """A bounded audio download.

    Attributes:
        path: The mp3 file. The caller owns it (move or delete it after ingest).
        title: The source's title, or the file stem when it has none.
        duration_s: Length in seconds, ``None`` when the source did not say.
        notice: The copyright notice to store with the file.
        info: Trimmed source metadata (see ``DownloadResult.info``).
    """

    path: Path
    title: str
    duration_s: float | None
    notice: str
    info: dict[str, Any]


def _bounds_opts(max_bytes: int) -> dict[str, Any]:
    return {
        "max_filesize": max_bytes,  # yt-dlp skips/aborts oversized formats
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": AUDIO_CODEC,
                "preferredquality": AUDIO_QUALITY,
            }
        ],
    }


def _mp3_path(path: Path) -> Path:
    """The extractor rewrites the download to ``.mp3``; ``path`` may name the original."""
    if path.suffix.lower() == f".{AUDIO_CODEC}":
        return path
    converted = path.with_suffix(f".{AUDIO_CODEC}")
    return converted if converted.exists() else path


def download_audio_bounded(
    url: str,
    *,
    download_dir: PathLike,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_duration_s: float = DEFAULT_MAX_DURATION_S,
    validate_target: TargetValidator = require_http_url,
    extra_opts: Mapping[str, Any] | None = None,
    cookies_file: CookiesFile = None,
    notice: str = COPYRIGHT_NOTICE,
) -> AudioDownload:
    """Download the audio of ``url`` as mp3, refusing what exceeds the caps.

    Order: ``validate_target`` (before any network), a metadata-only fetch to
    check the duration (before any media bytes), then the download with
    ``max_filesize``, then a size check on the extracted file.

    Args:
        url: A page link (YouTube, SoundCloud, Bandcamp, ...).
        download_dir: Where the mp3 is written (use a scratch directory).
        max_bytes: Cap on the downloaded and on the extracted file.
        max_duration_s: Cap on the source's duration. A source that reports no
            duration passes this check and is bounded by ``max_bytes`` alone.
        validate_target: Raises ``ValueError`` to refuse ``url``; see
            :func:`require_http_url`.
        extra_opts: Deployment yt-dlp options (credentials, cookies, proxy). The
            caps are applied after these and cannot be overridden by them.
        cookies_file: As in :func:`~yb.download.download_youtube_video`.
        notice: Copyright notice returned in the result.

    Raises:
        ValueError: ``validate_target`` refused ``url``, or a cap is not positive.
        AudioLimitError: The source is too long or the file too large.
    """
    if max_bytes <= 0 or max_duration_s <= 0:
        raise ValueError("max_bytes and max_duration_s must be positive")
    validate_target(url)

    deployment_opts = dict(extra_opts or {})
    preview = youtube_video_info(
        url, extra_opts=deployment_opts, cookies_file=cookies_file
    )
    duration = preview.get("duration")
    if isinstance(duration, (int, float)) and duration > max_duration_s:
        raise AudioLimitError(
            f"source is {int(duration)}s long; exceeds the {max_duration_s}s limit"
        )

    result = download_youtube_video(
        url,
        download_dir=download_dir,
        fmt="bestaudio/best",
        merge_to=None,
        extra_opts={**deployment_opts, **_bounds_opts(max_bytes)},
        cookies_file=cookies_file,
    )
    path = _mp3_path(Path(result.path))
    # max_filesize bounds the download, not the extracted output.
    if path.stat().st_size > max_bytes:
        path.unlink(missing_ok=True)
        raise AudioLimitError(f"downloaded audio exceeds the {max_bytes}-byte limit")
    info = result.info or {}
    return AudioDownload(
        path=path,
        title=info.get("title") or path.stem,
        duration_s=info.get("duration"),
        notice=notice,
        info=info,
    )

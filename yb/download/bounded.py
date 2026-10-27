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

import shutil
import tempfile
import urllib.parse
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from yb.download.youtube import (
    CookiesFile,
    PathLike,
    _extract_info,
    download_youtube_video,
)

#: Default byte cap. Above the mp3 size of a source at the default duration cap
#: (45 min at 192 kbps is about 65 MB), so a source that passes one passes both.
DEFAULT_MAX_BYTES = 80 * 1024 * 1024

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

#: yt-dlp options a deployment may pass in ``extra_opts``: how to reach and
#: authenticate to the source, nothing about what is fetched or where it goes.
DEPLOYMENT_OPT_KEYS = frozenset(
    {
        "cookiefile",
        "cookiesfrombrowser",
        "http_headers",
        "proxy",
        "username",
        "password",
        "extractor_args",
        "source_address",
        "js_runtimes",
        "remote_components",
    }
)

#: ``_type`` values of a result that holds several media (refused).
_MULTI_TYPES = frozenset({"playlist", "multi_video"})

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


def _mp3_path(path: Path) -> Path:
    """The extractor rewrites the download to ``.mp3``; ``path`` may name the original."""
    if path.suffix.lower() == f".{AUDIO_CODEC}":
        return path
    converted = path.with_suffix(f".{AUDIO_CODEC}")
    return converted if converted.exists() else path


def _pinned_opts(max_bytes: int, max_duration_s: float) -> dict[str, Any]:
    """Everything that makes this one bounded, single, non-live mp3 download."""
    from yt_dlp.utils import match_filter_func

    return {
        "max_filesize": max_bytes,  # yt-dlp skips/aborts oversized formats
        "noplaylist": True,
        "playlist_items": "1",
        "max_downloads": 1,
        "keepvideo": False,
        # `<=?` lets a source with no reported duration through; `!is_live` and
        # the byte cap bound it.
        "match_filter": match_filter_func(
            f"duration <=? {max_duration_s} & !is_live & !is_upcoming"
        ),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": AUDIO_CODEC,
                "preferredquality": AUDIO_QUALITY,
            }
        ],
    }


def _check_deployment_opts(extra_opts: Mapping[str, Any]) -> dict[str, Any]:
    unknown = sorted(set(extra_opts) - DEPLOYMENT_OPT_KEYS)
    if unknown:
        raise ValueError(
            f"extra_opts may only set {sorted(DEPLOYMENT_OPT_KEYS)}; got {unknown}"
        )
    return dict(extra_opts)


def _check_preview(preview: dict | None, *, max_duration_s: float) -> None:
    """Refuse multi-media, live, or over-long sources from their metadata."""
    preview = preview or {}
    if preview.get("_type") in _MULTI_TYPES or preview.get("entries"):
        raise AudioLimitError("playlists are not supported; pass a single video link")
    if preview.get("is_live") or preview.get("live_status") in {
        "is_live",
        "is_upcoming",
    }:
        raise AudioLimitError("live streams are not supported")
    duration = preview.get("duration")
    if isinstance(duration, (int, float)) and duration > max_duration_s:
        raise AudioLimitError(
            f"source is {int(duration)}s long; exceeds the {max_duration_s}s limit"
        )


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
    """Download the audio of one video link as mp3, refusing what exceeds the caps.

    Order: ``validate_target`` on ``url`` (before any network), a metadata-only
    fetch that refuses playlists, live streams and over-long sources (before any
    media bytes) and re-validates the resolved page URL, then the download with
    the caps pinned, then a size check on the extracted file. Work happens in a
    private temp directory under ``download_dir``, removed on any failure.

    Args:
        url: A page link (YouTube, SoundCloud, Bandcamp, ...).
        download_dir: Where the mp3 ends up (the caller owns it from then on).
        max_bytes: Cap on the downloaded and on the extracted file.
        max_duration_s: Cap on the source's duration. A source that reports no
            duration passes this check and is bounded by ``max_bytes`` alone.
        validate_target: Raises ``ValueError`` to refuse a URL; see
            :func:`require_http_url`. Not an egress sandbox: yt-dlp follows
            redirects itself.
        extra_opts: Deployment yt-dlp options, restricted to
            :data:`DEPLOYMENT_OPT_KEYS` (credentials, cookies, proxy); anything
            else raises, so no option can widen a cap or redirect the output.
        cookies_file: As in :func:`~yb.download.download_youtube_video`.
        notice: Copyright notice returned in the result.

    Raises:
        ValueError: ``validate_target`` refused a URL, a cap is not positive, or
            ``extra_opts`` has a key outside :data:`DEPLOYMENT_OPT_KEYS`.
        AudioLimitError: Playlist, live stream, too long, or too large.
    """
    if max_bytes <= 0 or max_duration_s <= 0:
        raise ValueError("max_bytes and max_duration_s must be positive")
    deployment_opts = _check_deployment_opts(extra_opts or {})
    validate_target(url)

    preview = _extract_info(
        url,
        {"quiet": True, "skip_download": True, "noplaylist": True},
        extra_opts=deployment_opts,
        cookies_file=cookies_file,
    )
    _check_preview(preview, max_duration_s=max_duration_s)
    if resolved := (preview or {}).get("webpage_url"):
        validate_target(resolved)

    out_dir = Path(download_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".yb-audio-", dir=out_dir))
    try:
        result = download_youtube_video(
            url,
            download_dir=work,
            fmt="bestaudio/best",
            merge_to=None,
            extra_opts={**deployment_opts, **_pinned_opts(max_bytes, max_duration_s)},
            cookies_file=cookies_file,
        )
        path = _mp3_path(Path(result.path))
        if path.suffix.lower() != f".{AUDIO_CODEC}" or not path.is_file():
            raise AudioLimitError(
                "source was rejected by the limits (no audio produced)"
            )
        # max_filesize bounds the download, not the extracted output.
        if path.stat().st_size > max_bytes:
            raise AudioLimitError(f"audio exceeds the {max_bytes}-byte limit")
        final = out_dir / path.name
        shutil.move(path, final)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    info = result.info or {}
    return AudioDownload(
        path=final,
        title=info.get("title") or final.stem,
        duration_s=info.get("duration"),
        notice=notice,
        info=info,
    )

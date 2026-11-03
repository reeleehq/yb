"""Link-to-audio with the safety policy applied once: :func:`download_audio_bounded`.

A service that turns a user-supplied link into an audio file (an MCP tool, an
ingest endpoint) needs the same guard rails every time: refuse bad targets before
touching the network, check every URL yt-dlp then requests (not only the first),
refuse over-long sources before fetching a byte, cap the bytes and the wall-clock
time even when the size is unknown, always produce mp3, send no ambient cookies,
and carry a copyright notice with the file. That policy lives here so a second
consumer does not copy it.

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
import time
import urllib.parse
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from yb.download.pacing import explain_rate_limit
from yb.download.youtube import (
    CookiesFile,
    PathLike,
    _resolve_output_path,
    _trim_info,
    _youtube_dl_cls,
    youtube_dl,
)

#: Default byte cap. Above the mp3 size of a source at the default duration cap
#: (45 min at 192 kbps is about 65 MB), so a source that passes one passes both.
DEFAULT_MAX_BYTES = 80 * 1024 * 1024

#: Default duration cap, in seconds (refuses livestream-length and multi-hour sources).
DEFAULT_MAX_DURATION_S = 45 * 60

#: Default wall-clock budget for the whole call (metadata, download, conversion
#: start), in seconds. Bounds a stream that trickles bytes under every other cap.
DEFAULT_TIMEOUT_S = 10 * 60

#: Media protocols whose bytes yt-dlp fetches itself (through the request guard).
#: Others (rtmp, rtsp, ...) are handed to an external program that the guard
#: cannot see, so their formats are never selected.
GUARDED_PROTOCOLS = ("https", "http", "m3u8_native", "m3u8", "http_dash_segments")

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
    """The source exceeds a cap (duration, size or time); nothing is left on disk."""


class AudioSourceError(ValueError):
    """yt-dlp could not get audio from the link (unsupported, unavailable, ...)."""


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
        path: The mp3 file, alone in its own directory. The caller owns the
            directory (``path.parent``): move the file, then remove it.
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


def _format_selector(protocols: tuple[str, ...]) -> str:
    """Best audio, else best, restricted to ``protocols``."""
    only = "[protocol~='^(%s)$']" % "|".join(protocols)
    return f"bestaudio{only}/best{only}"


def _pinned_opts(
    work: Path, *, max_bytes: int, max_duration_s: float, deadline: float
) -> dict[str, Any]:
    """Everything that makes this one bounded, single, non-live mp3 download."""
    from yt_dlp.utils import match_filter_func

    return {
        "quiet": True,
        "noprogress": True,
        "format": _format_selector(GUARDED_PROTOCOLS),
        "outtmpl": str(work / "%(title)s (%(id)s).%(ext)s"),
        "max_filesize": max_bytes,  # yt-dlp skips/aborts formats of known size
        "progress_hooks": [_byte_and_time_cap(max_bytes, deadline)],
        # HLS the native downloader cannot handle is delegated to ffmpeg, which
        # fetches segments itself, unguarded: let it read local files only.
        "external_downloader_args": {"ffmpeg_i": ["-protocol_whitelist", "file"]},
        "noplaylist": True,
        "playlist_items": "1",
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


def _check_deadline(deadline: float) -> None:
    if time.monotonic() > deadline:
        raise AudioLimitError("the download took longer than its time limit")


def _byte_and_time_cap(max_bytes: int, deadline: float) -> Callable[[dict], None]:
    """A yt-dlp progress hook that aborts past ``max_bytes`` or ``deadline``.

    ``max_filesize`` only acts on a size known up front; this bounds a chunked
    stream of unknown length as its bytes arrive.
    """

    def hook(status: dict) -> None:
        if (status.get("downloaded_bytes") or 0) > max_bytes:
            raise AudioLimitError(f"download exceeds the {max_bytes}-byte limit")
        _check_deadline(deadline)

    return hook


def _guard_requests(ydl: Any, validate: TargetValidator, deadline: float) -> None:
    """Check every URL ``ydl`` requests (pages, manifests, media) before and after.

    Extractors and yt-dlp's own downloaders all go through ``ydl.urlopen``, so
    wrapping it covers every hop, not only the link the caller passed. The URL a
    response ends at (after redirects, which the HTTP layer follows itself) is
    checked too, so a redirect into a refused host never yields its content.
    """
    urlopen = ydl.urlopen

    def guarded(req):
        _check_deadline(deadline)
        validate(req if isinstance(req, str) else req.url)
        response = urlopen(req)
        final = getattr(response, "url", None)
        if final:
            try:
                validate(final)
            except BaseException:
                response.close()
                raise
        return response

    ydl.urlopen = guarded


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


@contextmanager
def _typed_errors() -> Iterator[None]:
    """Our own refusals pass through; any other yt-dlp error is an :class:`AudioSourceError`.

    yt-dlp sometimes wraps an exception raised in a hook or the request guard in
    its own ``DownloadError``; the original is unwrapped so the caller sees the
    refusal (``ValueError`` from ``validate_target``, :class:`AudioLimitError`).
    """
    from yt_dlp.utils import YoutubeDLError

    try:
        yield
    except YoutubeDLError as exc:
        cause = (getattr(exc, "exc_info", None) or (None, None))[1]
        if isinstance(cause, ValueError):
            raise cause from exc
        raise AudioSourceError(str(exc)) from exc


def download_audio_bounded(
    url: str,
    *,
    download_dir: PathLike,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_duration_s: float = DEFAULT_MAX_DURATION_S,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    validate_target: TargetValidator = require_http_url,
    extra_opts: Mapping[str, Any] | None = None,
    cookies_file: CookiesFile = False,
    notice: str = COPYRIGHT_NOTICE,
) -> AudioDownload:
    """Download the audio of one video link as mp3, refusing what exceeds the caps.

    Order: ``validate_target`` on ``url`` (before any network); one yt-dlp
    session whose every request (page, embedded page, manifest, media, fragment)
    passes ``validate_target`` first, and whose final URL after redirects does
    too; a metadata pass that refuses playlists, live streams and over-long
    sources before any media bytes; the download of those same formats (no
    second extraction), aborted past ``max_bytes`` or ``timeout_s`` even when
    the size is unknown; a size check on the extracted file. The mp3 is written
    to a fresh private directory under ``download_dir`` (so concurrent calls
    never collide); on any failure that directory is removed.

    Args:
        url: A page link (YouTube, SoundCloud, Bandcamp, ...).
        download_dir: Parent of the per-call directory holding the mp3 (the caller
            owns that directory from then on and removes it after ingest).
        max_bytes: Cap on the downloaded and on the extracted file.
        max_duration_s: Cap on the source's duration. A source that reports no
            duration passes this check and is bounded by ``max_bytes`` and
            ``timeout_s``.
        timeout_s: Wall-clock budget for fetching, checked on every request and
            every received chunk (a stalled connection is bounded by yt-dlp's
            socket timeout).
        validate_target: Raises ``ValueError`` to refuse a URL; see
            :func:`require_http_url`. Applied to every URL yt-dlp requests. Not
            an egress sandbox: a redirect is followed by the HTTP layer before
            its target can be checked (its content is then refused), and the
            check sees a URL, not the address its host resolves to.
        extra_opts: Deployment yt-dlp options, restricted to
            :data:`DEPLOYMENT_OPT_KEYS` (credentials, cookies, proxy); anything
            else raises, so no option can widen a cap or redirect the output.
        cookies_file: As in :func:`~yb.download.download_youtube_video`, except
            the default is ``False``: a service fetching for remote users must
            not do it with the operator's account by accident. Pass a path (or
            ``None`` for yb's default file) to opt in.
        notice: Copyright notice returned in the result.

    Raises:
        ImportError: yt-dlp is not installed (with the install command), raised
            before any network.
        ValueError: ``validate_target`` refused a URL, a cap is not positive, or
            ``extra_opts`` has a key outside :data:`DEPLOYMENT_OPT_KEYS`.
        AudioLimitError: Playlist, live stream, too long, too large, or too slow.
        AudioSourceError: yt-dlp could not get audio from the link.
        RateLimitedError: The source is rate-limiting or bot-checking this
            client (a ``RuntimeError``: retry later, the link may be fine).
    """
    ydl_cls = _youtube_dl_cls()  # ImportError with the install hint, up front
    if max_bytes <= 0 or max_duration_s <= 0 or timeout_s <= 0:
        raise ValueError("max_bytes, max_duration_s and timeout_s must be positive")
    deployment_opts = _check_deployment_opts(extra_opts or {})
    validate_target(url)
    deadline = time.monotonic() + timeout_s

    out_dir = Path(download_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".yb-audio-", dir=out_dir))
    try:
        opts = _pinned_opts(
            work, max_bytes=max_bytes, max_duration_s=max_duration_s, deadline=deadline
        )
        with (
            youtube_dl(
                opts,
                extra_opts=deployment_opts,
                cookies_file=cookies_file,
                ydl_cls=ydl_cls,
            ) as ydl,
            _typed_errors(),
            explain_rate_limit(),
        ):
            _guard_requests(ydl, validate_target, deadline)
            preview = ydl.extract_info(url, download=False)
            _check_preview(preview, max_duration_s=max_duration_s)
            info = ydl.process_ie_result(preview, download=True)
            path = _mp3_path(_resolve_output_path(info, ydl, work, None))
        if path.suffix.lower() != f".{AUDIO_CODEC}" or not path.is_file():
            raise AudioLimitError(
                "source was rejected by the limits (no audio produced)"
            )
        # max_filesize and the progress hook bound the download, not the output.
        if path.stat().st_size > max_bytes:
            raise AudioLimitError(f"audio exceeds the {max_bytes}-byte limit")
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    trimmed = _trim_info(info)
    return AudioDownload(
        path=path,
        title=trimmed.get("title") or path.stem,
        duration_s=trimmed.get("duration"),
        notice=notice,
        info=trimmed,
    )

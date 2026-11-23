"""Link-to-audio with the safety policy applied once: :func:`download_audio_bounded`.

A service that turns a user-supplied link into an audio file (an MCP tool, an
ingest endpoint) needs the same guard rails every time: refuse bad targets before
touching the network, check every URL yt-dlp then requests (not only the first)
and every address it connects to (each redirect hop, after each name lookup),
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
import socket
import tempfile
import math
import time
import urllib.parse
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from yb.download.egress import address_check, no_address_check, url_of_address
from yb.download.pacing import explain_rate_limit
from yb.download.youtube import (
    CookiesFile,
    PathLike,
    resolve_output_path,
    trim_info,
    youtube_dl_cls,
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
#: Others (rtmp, rtsp, ffmpeg-only ``m3u8``, ...) are handed to an external
#: program that the guard cannot see, so their formats are never selected.
GUARDED_PROTOCOLS = ("https", "http", "m3u8_native", "http_dash_segments")

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
        "logger",
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


class AudioTargetError(ValueError):
    """``validate_target`` refused a URL: the link, or one yt-dlp was about to fetch."""


class AddressRefusedError(AudioTargetError, OSError):
    """``validate_target`` refused the address a connection was about to use.

    Also an ``OSError``, so the HTTP layer treats it as a failed connection (no
    retry on another request handler) and yt-dlp wraps it as a transport error.
    """


#: Request handlers whose every connection resolves through ``socket.getaddrinfo``
#: in the calling thread, where the connect-time check sits. Others (curl_cffi's,
#: whose libcurl resolves and follows redirects in C) are removed while it runs.
CHECKED_REQUEST_HANDLERS = frozenset({"Urllib", "Requests", "Websockets"})


def _validated(validate: TargetValidator, url: str) -> None:
    """Run ``validate`` on ``url``; its ``ValueError`` becomes an :class:`AudioTargetError`."""
    try:
        validate(url)
    except AudioTargetError:
        raise
    except ValueError as exc:
        raise AudioTargetError(str(exc)) from exc


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


MAX_FILENAME_CHARS = 100  # yt-dlp ``trim_file_name``: keeps names under OS limits (255)


def _format_selector(protocols: tuple[str, ...]) -> str:
    """Best audio, else best, restricted to ``protocols``."""
    only = "[protocol~='^(%s)$']" % "|".join(protocols)
    return f"bestaudio{only}/best{only}"


def _conversion_args(max_bytes: int, deadline: float) -> dict[str, list[str]]:
    """ffmpeg arguments that bound the mp3 conversion as the download is bounded.

    The byte cap bounds the download, but a small, highly compressible source (an
    hour of near-silent FLAC is a few hundred KB) decodes to far more mp3 than that,
    and a direct link reports no duration to refuse it by. So the conversion itself
    stops writing past ``max_bytes`` (``-fs``: the file ends just over the cap, which
    the size check then refuses), stops after the time left to the call in CPU
    seconds (``-timelimit``), and reads local files only (``-protocol_whitelist``:
    a downloaded playlist must not make ffmpeg fetch its segments).
    """
    seconds_left = max(1, math.ceil(deadline - time.monotonic()))
    return {
        "extractaudio+ffmpeg_i": ["-protocol_whitelist", "file"],
        "extractaudio+ffmpeg_o": [
            "-fs",
            str(max_bytes),
            "-timelimit",
            str(seconds_left),
        ],
    }


def _pinned_opts(work: Path, *, max_bytes: int, deadline: float) -> dict[str, Any]:
    """Everything that makes this one bounded, single, non-live mp3 download."""
    return {
        "quiet": True,
        "no_warnings": True,  # untrusted links must not fill a service's stderr
        "noprogress": True,
        "format": _format_selector(GUARDED_PROTOCOLS),
        "outtmpl": str(work / "%(title)s (%(id)s).%(ext)s"),
        # Direct links that redirect to a signed address get title/id from a URL
        # with a ~350-character signature: cap the name, not the caller's problem.
        "trim_file_name": MAX_FILENAME_CHARS,
        "max_filesize": max_bytes,  # yt-dlp skips/aborts formats of known size
        "progress_hooks": [_byte_and_time_cap(max_bytes, deadline)],
        # HLS the native downloader cannot handle is delegated to ffmpeg, which
        # fetches segments itself, unguarded: let it read local files only.
        "external_downloader_args": {"ffmpeg_i": ["-protocol_whitelist", "file"]},
        "noplaylist": True,
        "playlist_items": "1",
        # The connect-time address check is per thread: fragments stay on this one.
        "concurrent_fragment_downloads": 1,
        "keepvideo": False,
        "postprocessor_args": _conversion_args(max_bytes, deadline),
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
    The HTTP layer follows redirects itself, so the hops before the last never
    pass through here: :func:`_connect_guard` checks the address each of them
    connects to instead.
    """
    urlopen = ydl.urlopen

    def guarded(req):
        _check_deadline(deadline)
        with no_address_check():  # the URL check's own lookups are not connections
            _validated(validate, req if isinstance(req, str) else req.url)
        response = urlopen(req)
        final = getattr(response, "url", None)
        if final:
            try:
                with no_address_check():
                    _validated(validate, final)
            except BaseException:
                response.close()
                raise
        return response

    ydl.urlopen = guarded


def _address_rule(
    validate: TargetValidator, *, trusted: frozenset = frozenset()
) -> Callable[[str, int | None], None]:
    """``validate`` applied to the address a connection is about to use.

    The address goes in as an IP-literal URL (``http://10.0.0.1:443/``), so a
    validator that refuses internal addresses judges the address itself, with no
    second lookup to rebind: the address checked is the address connected to.
    ``trusted`` holds ``(ip, port)`` pairs that pass unchecked: the deployment's
    proxies, which the operator configured. Known residual: a direct (unproxied)
    connection to a proxy's own address and port passes too; a forward proxy
    answers such a request with an error, not content.
    """

    def check(ip: str, port: int | None) -> None:
        if not port or (ip, port) in trusted:
            # No port: a lookup, not a connection (every connect passes its port;
            # yt-dlp's socks4/socks5 resolve the target with none, for the proxy).
            return
        address = url_of_address(ip, port)
        try:
            validate(address)
        except Exception as exc:  # a validator's bug refuses too (fail closed)
            raise AddressRefusedError(
                f"refused to connect to {address} (an address a requested host "
                f"resolved to): {exc}"
            ) from exc

    return check


_PROXY_DEFAULT_PORTS = {
    "http": 80,
    "https": 443,
    "socks4": 1080,
    "socks4a": 1080,
    "socks5": 1080,
    "socks5h": 1080,
}


def _proxy_endpoints(ydl: Any) -> frozenset:
    """``(ip, port)`` of every proxy ``ydl`` may send requests through.

    From its ``proxy`` option or the ``*_PROXY`` environment (yt-dlp's ``proxies``
    map; its ``no`` entry is a bypass list, not a proxy). Connections to these
    pass the address check; connections that bypass a proxy are checked.
    """
    proxies = getattr(ydl, "proxies", None) or {}
    out = set()
    for key, value in proxies.items():
        if key == "no" or not value or value == "__noproxy__":
            continue
        parts = urllib.parse.urlparse(value if "://" in value else f"http://{value}")
        if not parts.hostname:
            continue
        port = parts.port or _PROXY_DEFAULT_PORTS.get(parts.scheme, 80)
        try:  # no check is active yet: this resolves directly
            infos = socket.getaddrinfo(parts.hostname, port, 0, socket.SOCK_STREAM)
        except OSError:
            continue  # unresolvable now: its connection is checked (and refused)
        out.update((info[4][0], port) for info in infos)
    return frozenset(out)


def _keep_checked_handlers(ydl: Any) -> None:
    """Remove the request handlers the connect-time check cannot see."""
    director = getattr(ydl, "_request_director", None)
    if director is None:  # a stand-in YoutubeDL (tests)
        return
    for key in list(director.handlers):
        if key not in CHECKED_REQUEST_HANDLERS:
            director.handlers.pop(key).close()


@contextmanager
def _connect_guard(validate: TargetValidator, ydl: Any) -> Iterator[None]:
    """Check every address ``ydl`` connects to with ``validate``, unless nothing needs it.

    Skipped for the default floor (:func:`require_http_url` accepts any address).
    Otherwise only request handlers that resolve in Python are kept (impersonation,
    which needs curl_cffi, is then unavailable: a request that requires it fails
    as a source error). Connections to the deployment's proxies pass: a proxy
    resolves the target itself, so the egress rule for proxied requests belongs
    there. Every direct connection, including one a ``no_proxy`` list sends
    around the proxy, is checked.
    """
    if validate is require_http_url:
        yield
        return
    _keep_checked_handlers(ydl)
    with address_check(_address_rule(validate, trusted=_proxy_endpoints(ydl))):
        yield


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
    its own ``DownloadError``; only *our* refusals (:class:`AudioTargetError`,
    :class:`AudioLimitError`) are unwrapped. Any other cause, such as an
    extractor's own ``ValueError`` on a malformed page, is a source error.
    """
    from yt_dlp.utils import YoutubeDLError

    try:
        yield
    except YoutubeDLError as exc:
        cause = _our_refusal(exc)
        if cause is not None:
            raise cause from exc
        raise AudioSourceError(str(exc)) from exc


def _our_refusal(exc: BaseException) -> BaseException | None:
    """Our refusal inside a yt-dlp error, if any.

    yt-dlp keeps the cause in ``exc_info`` (a hook's error) or chains it (a request
    handler wraps an error raised while connecting, such as the connect-time
    address check's, in its own ``RequestError``).
    """
    seen: set[int] = set()
    stack = [exc]
    while stack:
        e = stack.pop()
        if e is None or id(e) in seen:
            continue
        seen.add(id(e))
        if isinstance(e, (AudioTargetError, AudioLimitError)):
            return e
        stack += [
            (getattr(e, "exc_info", None) or (None, None))[1],
            e.__cause__,
            e.__context__,
        ]
    return None


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
    passes ``validate_target`` first, whose every connection (each redirect hop
    included) goes only to an address ``validate_target`` accepts, and whose
    final URL after redirects passes it too; a metadata pass that refuses playlists, live streams and over-long
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
            :func:`require_http_url`. Applied to every URL yt-dlp requests, and
            to every address it connects to, as an IP-literal URL
            (``http://10.0.0.1:443/``; see :mod:`yb.download.egress`), so a
            validator that refuses internal addresses also stops DNS rebinding
            and redirect hops into them before they connect. With a validator
            other than the default, impersonation (curl_cffi) is not used, since
            libcurl resolves out of the check's reach. A connection to the
            deployment's proxy (``extra_opts["proxy"]`` or the ``*_PROXY``
            environment) passes: the proxy connects to the target, so the egress
            rule for proxied requests belongs there.
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
        AudioTargetError: ``validate_target`` refused a URL (a ``ValueError``).
        ValueError: A cap is not positive, or ``extra_opts`` has a key outside
            :data:`DEPLOYMENT_OPT_KEYS`.
        AudioLimitError: Playlist, live stream, too long, too large, or too slow.
        AudioSourceError: yt-dlp could not get audio from the link.
        RateLimitedError: The source is rate-limiting or bot-checking this
            client (a ``RuntimeError``: retry later, the link may be fine).
    """
    ydl_cls = youtube_dl_cls()  # ImportError with the install hint, up front
    if max_bytes <= 0 or max_duration_s <= 0 or timeout_s <= 0:
        raise ValueError("max_bytes, max_duration_s and timeout_s must be positive")
    deployment_opts = _check_deployment_opts(extra_opts or {})
    _validated(validate_target, url)
    deadline = time.monotonic() + timeout_s

    out_dir = Path(download_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".yb-audio-", dir=out_dir))
    try:
        opts = _pinned_opts(work, max_bytes=max_bytes, deadline=deadline)
        with (
            youtube_dl(
                opts,
                extra_opts=deployment_opts,
                cookies_file=cookies_file,
                ydl_cls=ydl_cls,
            ) as ydl,
            _connect_guard(validate_target, ydl),
            _typed_errors(),
            explain_rate_limit(),
        ):
            _guard_requests(ydl, validate_target, deadline)
            preview = ydl.extract_info(url, download=False)
            _check_preview(preview, max_duration_s=max_duration_s)
            info = ydl.process_ie_result(preview, download=True)
            path = _mp3_path(resolve_output_path(info, ydl, work, None))
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
    trimmed = trim_info(info)
    return AudioDownload(
        path=path,
        title=trimmed.get("title") or path.stem,
        duration_s=trimmed.get("duration"),
        notice=notice,
        info=trimmed,
    )

"""Download YouTube videos (and their metadata) via yt-dlp.

The common case is one call — ``download_youtube_video(url)`` — which fetches
the best video+audio into ``~/Downloads`` as ``Title (video_id).mp4``. Every
knob (destination, format, filename template, and which sidecar metadata to
also save) is overridable, and any raw yt-dlp option can be passed through.

The destination defaults to ``$YB_DOWNLOAD_DIR`` when set, else ``~/Downloads``.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import warnings
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from yb.download.ranges import (
    INFO_RANGE_KEY,
    TimeRange,
    Timestamp,
    range_opts,
    ranged_filename_template,
)
from yb.download.pacing import Pace, explain_rate_limit, pace_opts
from yb.download.requirements import with_runtime_opts

PathLike = str | Path

#: What :func:`download_youtube_audio` does when a format conversion fails.
OnConvertError = Literal["raise", "warn"]

_ON_CONVERT_ERROR_CHOICES = frozenset({"raise", "warn"})

#: Env var that overrides the default download directory.
DOWNLOAD_DIR_ENV = "YB_DOWNLOAD_DIR"

#: Env var naming a Netscape-format cookies file to authenticate downloads with.
COOKIES_FILE_ENV = "YB_COOKIES_FILE"

#: Env var: when truthy (``1``/``true``/``yes``), each call hands yt-dlp a private
#: temporary copy of the cookies file instead of the file itself (see
#: :func:`_final_opts`). Set it for parallel workers sharing one file.
COOKIES_PRIVATE_COPY_ENV = "YB_COOKIES_PRIVATE_COPY"

#: Values of :data:`COOKIES_PRIVATE_COPY_ENV` that turn it on.
_TRUTHY = frozenset({"1", "true", "yes"})

#: Cookies file used when :data:`COOKIES_FILE_ENV` is unset and this file exists.
DEFAULT_COOKIES_FILE = "~/.config/yb/youtube-cookies.txt"

#: yt-dlp options that already say where cookies come from (so no default is added).
_COOKIE_OPT_KEYS = ("cookiefile", "cookiesfrombrowser")

#: What ``cookies_file`` accepts: a path, ``None`` (look for a default), or ``False`` (none).
CookiesFile = PathLike | Literal[False] | None

#: yt-dlp output template: human title plus the stable id, e.g. "My Talk (dQw4...).mp4".
DEFAULT_OUTTMPL = "%(title)s (%(id)s).%(ext)s"

#: Template for ``item_folders=True``: ``001_<id>/<id>.<ext>``, sidecars beside it.
ITEM_FOLDER_OUTTMPL = "%(playlist_index)03d_%(id)s/%(id)s.%(ext)s"

#: yt-dlp format selector for the best audio-only stream.
DEFAULT_AUDIO_FMT = "bestaudio/best"

#: Fields surfaced on the result's ``info`` (the rest of yt-dlp's dict is dropped).
_INFO_FIELDS = (
    "id",
    "title",
    "uploader",
    "channel",
    "channel_id",
    "duration",
    "upload_date",
    "view_count",
    "like_count",
    "description",
    "tags",
    "categories",
    "chapters",
    "webpage_url",
    "original_url",
    "thumbnail",
    "language",
    "fps",
    "width",
    "height",
)


def default_download_dir() -> Path:
    """Resolve the default download directory (``$YB_DOWNLOAD_DIR`` or ``~/Downloads``)."""
    override = os.environ.get(DOWNLOAD_DIR_ENV)
    if override:
        return Path(override).expanduser()
    return Path.home() / "Downloads"


@dataclass
class DownloadResult:
    """Outcome of a download.

    Attributes:
        path: The downloaded media file.
        info: A trimmed metadata dict (see :data:`_INFO_FIELDS`).
        sidecars: Map of extra artifacts written (``info_json``, ``thumbnail``,
            ``description``, ``subtitles`` → path(s)).
    """

    path: Path
    info: dict[str, Any]
    sidecars: dict[str, Any] = field(default_factory=dict)

    @property
    def video_id(self) -> str:
        """The YouTube video id."""
        return self.info.get("id", "")


def default_cookies_file() -> Path | None:
    """The cookies file downloads use when none is passed, or ``None``.

    ``$YB_COOKIES_FILE`` if set, else ``~/.config/yb/youtube-cookies.txt`` if it
    exists. A file named by the env var that does not exist is skipped with a
    warning (a typo should not silently fall back to anonymous downloads).
    """
    named = os.environ.get(COOKIES_FILE_ENV)
    if named:
        path = Path(named).expanduser()
        if path.is_file():
            return path
        warnings.warn(
            f"${COOKIES_FILE_ENV} points to a file that does not exist; "
            "downloading without cookies.",
            stacklevel=4,
        )
        return None
    path = Path(DEFAULT_COOKIES_FILE).expanduser()
    return path if path.is_file() else None


#: Fields on a cookie line of a Netscape cookies file (tab-separated).
_COOKIE_FIELDS = 7


def _malformed_cookie_lines(path: Path) -> list[int]:
    """1-based numbers of the lines yt-dlp would reject (never their content).

    yt-dlp prints a rejected line verbatim to stderr, cookie value included and
    whatever ``quiet`` says, so yb checks the file first and reports line numbers.
    """
    bad = []
    for n, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
        stripped = line.strip()
        if not stripped or (
            stripped.startswith("#") and not stripped.startswith("#HttpOnly_")
        ):
            continue
        if len(line.split("\t")) != _COOKIE_FIELDS:
            bad.append(n)
    return bad


def _usable_cookies_file(path: Path, *, explicit: bool) -> str | None:
    """``str(path)`` if it is a well-formed cookies file, else raise / warn+``None``."""
    bad = _malformed_cookie_lines(path)
    if not bad:
        return str(path)
    msg = (
        f"cookies file {path} is not in Netscape format "
        f"(malformed line(s): {bad[:5]}); fields must be tab-separated."
    )
    if explicit:
        raise ValueError(msg)
    warnings.warn(msg + " Downloading without cookies.", stacklevel=4)
    return None


def _cookie_opts(
    cookies_file: CookiesFile,
    *,
    cookies_from_browser: str | tuple | None = None,
    extra_opts: dict | None = None,
) -> dict[str, Any]:
    """yt-dlp cookie options for ``cookies_file`` (merge these *before* ``extra_opts``).

    An explicit ``cookies_file`` is used as given (``FileNotFoundError`` if it is
    missing). The default file (:func:`default_cookies_file`) is used only when
    nothing else says where cookies come from: no ``cookies_from_browser`` and no
    ``cookiefile`` / ``cookiesfrombrowser`` in ``extra_opts``. ``False`` opts out.
    """
    if cookies_file is False:
        return {}
    if cookies_file is not None:
        path = Path(cookies_file).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"cookies_file not found: {path}")
        if cookies_from_browser or "cookiesfrombrowser" in (extra_opts or {}):
            # yt-dlp would merge the browser's whole jar into this file on exit.
            raise ValueError(
                "cookies_file cannot be combined with a browser cookie source: "
                "yt-dlp would write the browser's cookies into the file."
            )
        return {"cookiefile": _usable_cookies_file(path, explicit=True)}
    if cookies_from_browser or any(k in (extra_opts or {}) for k in _COOKIE_OPT_KEYS):
        return {}
    path = default_cookies_file()
    usable = _usable_cookies_file(path, explicit=False) if path else None
    return {"cookiefile": usable} if usable else {}


def _wants_private_cookie_copy(path: str) -> bool:
    """Whether yt-dlp must not get ``path`` itself: unwritable, or the env asks."""
    env = os.environ.get(COOKIES_PRIVATE_COPY_ENV, "").strip().lower()
    return env in _TRUTHY or not os.access(path, os.W_OK)


@contextmanager
def _final_opts(
    opts: dict[str, Any],
    cookie_opts: dict[str, Any],
    extra_opts: dict | None,
):
    """Yield the merged yt-dlp options (``opts``, cookies, then ``extra_opts``).

    yt-dlp rewrites its ``cookiefile`` on exit, so a file that is readable but
    not writable (a read-only secret mount) makes it raise ``PermissionError``
    after a successful download, and parallel workers sharing one file can leave
    it half-written. Whatever the cookie file's source (``cookies_file``, the
    default, or ``extra_opts``), in those cases (or when
    :data:`COOKIES_PRIVATE_COPY_ENV` is set) yt-dlp gets a 0600 temporary copy,
    deleted on exit; the cookies it refreshes are then not persisted back.
    """
    merged = {**opts, **cookie_opts, **(extra_opts or {})}
    source = merged.get("cookiefile")
    # A missing path is left for yt-dlp to report.
    if not (source and Path(source).is_file() and _wants_private_cookie_copy(source)):
        yield merged
        return
    fd, copy = tempfile.mkstemp(prefix="yb-cookies-", suffix=".txt")  # mode 0600
    try:
        with os.fdopen(fd, "wb") as out, open(source, "rb") as src:
            shutil.copyfileobj(src, out)
        yield {**merged, "cookiefile": copy}
    finally:
        Path(copy).unlink(missing_ok=True)


def _extract_info(
    target: str,
    base_opts: dict[str, Any],
    *,
    extra_opts: dict | None,
    cookies_file: CookiesFile,
) -> dict | None:
    """Metadata-only yt-dlp extraction: cookies, then ``extra_opts``, then the JS runtime."""
    from yt_dlp import YoutubeDL

    cookie_opts = _cookie_opts(cookies_file, extra_opts=extra_opts)
    with _final_opts(base_opts, cookie_opts, extra_opts) as opts:
        with YoutubeDL(with_runtime_opts(opts)) as ydl:
            return ydl.extract_info(target, download=False)


def youtube_video_info(
    url: str,
    *,
    extra_opts: dict | None = None,
    cookies_file: CookiesFile = None,
) -> dict[str, Any]:
    """Fetch a video's metadata without downloading it.

    Returns the trimmed info dict (see :data:`_INFO_FIELDS`). Useful to preview
    the title/duration/chapters before deciding to download.

    ``cookies_file``: see :func:`download_youtube_video`.
    """
    info = _extract_info(
        url,
        {"quiet": True, "skip_download": True, "noplaylist": True},
        extra_opts=extra_opts,
        cookies_file=cookies_file,
    )
    return _trim_info(info)


def download_youtube_video(
    url: str,
    *,
    download_dir: PathLike | None = None,
    fmt: str = "bestvideo+bestaudio/best",
    merge_to: str | None = "mp4",
    filename_template: str = DEFAULT_OUTTMPL,
    write_info_json: bool = False,
    write_thumbnail: bool = False,
    write_description: bool = False,
    write_subtitles: bool = False,
    write_auto_subtitles: bool = False,
    subtitle_langs: tuple[str, ...] = ("en",),
    quiet: bool = True,
    extra_opts: dict | None = None,
    start: Timestamp | None = None,
    end: Timestamp | None = None,
    precise_cuts: bool = False,
    cookies_file: CookiesFile = None,
    pace: Pace | str | None = None,
) -> DownloadResult:
    """Download a YouTube video to ``download_dir`` (default ``~/Downloads``).

    Simplest use: ``download_youtube_video(url)`` → best quality merged to mp4,
    named ``Title (video_id).mp4`` in ``~/Downloads``.

    Args:
        url: The video URL (or id).
        download_dir: Destination directory. Defaults to
            :func:`default_download_dir`.
        fmt: yt-dlp format selector (default best video + best audio).
        merge_to: Container to merge video+audio into (default ``"mp4"``;
            requires ffmpeg). Set ``None`` to keep yt-dlp's default.
        filename_template: yt-dlp output template (default
            ``"%(title)s (%(id)s).%(ext)s"``).
        write_info_json: Also save the full metadata as ``*.info.json``.
        write_thumbnail: Also save the thumbnail image.
        write_description: Also save the description as ``*.description``.
        write_subtitles: Also save uploaded subtitles for ``subtitle_langs``.
        write_auto_subtitles: Also save auto-generated subtitles.
        subtitle_langs: Subtitle languages to fetch when subtitles are enabled.
        quiet: Suppress yt-dlp console output.
        extra_opts: Any additional raw yt-dlp options (merged last, so they win).
        start, end: Download only this span: seconds (``7.9``) or a timestamp
            (``"0:07.9"``, ``"1:02:03"``). Either may be given alone (``end``
            only = from the beginning; ``start`` only = to the end). The span
            is recorded in ``info["download_range"]`` as ``{"start", "end"}``
            seconds (``end`` is ``None`` for "to the end"), and, with the
            default ``filename_template``, in the filename (``Title (id)
            [7.9-8.75].mp4``) so a clip never collides with the full video.
            Needs ffmpeg (see :mod:`yb.download.ranges`).
        precise_cuts: With ``start``/``end``, re-encode at the cuts for
            frame-accurate bounds (slower) instead of cutting at keyframes.
        cookies_file: Netscape-format cookies file to authenticate with (for
            headless servers where ``cookies_from_browser`` cannot work). Default
            ``None`` reads ``$YB_COOKIES_FILE``, else
            ``~/.config/yb/youtube-cookies.txt`` if it exists, else sends no
            cookies. An explicit ``cookies_from_browser`` or ``extra_opts``
            cookie option suppresses that default; ``False`` opts out of it.
            The file is checked first (``ValueError`` if explicit, else a
            warning, naming only line numbers). It cannot be combined with a
            browser cookie source. yt-dlp rewrites the file with refreshed
            cookies on exit, so a file that is not writable is handed over as a
            private temporary copy instead, as is every file when
            ``$YB_COOKIES_PRIVATE_COPY`` is truthy (use it for parallel workers
            sharing one file); refreshed cookies are then not persisted.
        pace: Be gentle with YouTube: a :class:`~yb.download.pacing.Pace` or a
            preset name (``"polite"``: sleep 20-60 s between items, 1 s between
            requests, 4 MB/s cap). Default ``None`` adds nothing. Raw yt-dlp
            options in ``extra_opts`` win over it.

    Returns:
        A :class:`DownloadResult` with the media path, trimmed ``info``, and any
        ``sidecars`` written.

    Raises:
        ValueError: If ``start``/``end`` is not a timestamp, or ``end`` is not
            after ``start``. Raised before anything is fetched or written.
    """
    time_range = TimeRange.of(start=start, end=end)
    if time_range is None and precise_cuts:
        raise ValueError("precise_cuts needs a start and/or end to cut at")

    from yt_dlp import YoutubeDL

    out_dir = Path(download_dir) if download_dir else default_download_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    opts: dict[str, Any] = {
        "format": fmt,
        "outtmpl": str(out_dir / filename_template),
        "noplaylist": True,
        "quiet": quiet,
        "writeinfojson": write_info_json,
        "writethumbnail": write_thumbnail,
        "writedescription": write_description,
        "writesubtitles": write_subtitles,
        "writeautomaticsub": write_auto_subtitles,
        "subtitleslangs": list(subtitle_langs),
    }
    if merge_to:
        opts["merge_output_format"] = merge_to
    if time_range:
        opts.update(range_opts(time_range, precise_cuts=precise_cuts))
        if filename_template == DEFAULT_OUTTMPL:
            opts["outtmpl"] = str(
                out_dir
                / ranged_filename_template(
                    filename_template, time_range, precise_cuts=precise_cuts
                )
            )
    opts.update(pace_opts(pace))

    cookie_opts = _cookie_opts(cookies_file, extra_opts=extra_opts)
    with _final_opts(opts, cookie_opts, extra_opts) as final:
        with explain_rate_limit(), YoutubeDL(with_runtime_opts(final)) as ydl:
            info = ydl.extract_info(url, download=True)

    path = _resolve_output_path(info, ydl, out_dir, merge_to)
    sidecars = _collect_sidecars(
        info,
        path,
        info_json=write_info_json,
        thumbnail=write_thumbnail,
        description=write_description,
        subtitles=write_subtitles or write_auto_subtitles,
    )
    trimmed = _trim_info(info)
    if time_range and "download_ranges" not in (extra_opts or {}):
        trimmed[INFO_RANGE_KEY] = time_range.as_info()
    return DownloadResult(path=path, info=trimmed, sidecars=sidecars)


def download_youtube_audio(
    url: str,
    *,
    download_dir: PathLike | None = None,
    audio_format: str | None = None,
    bitrate: str | None = None,
    keep_original: bool = False,
    on_error: OnConvertError = "raise",
    fmt: str = DEFAULT_AUDIO_FMT,
    filename_template: str = DEFAULT_OUTTMPL,
    write_info_json: bool = False,
    write_thumbnail: bool = False,
    write_description: bool = False,
    write_subtitles: bool = False,
    write_auto_subtitles: bool = False,
    subtitle_langs: tuple[str, ...] = ("en",),
    quiet: bool = True,
    extra_opts: dict | None = None,
    start: Timestamp | None = None,
    end: Timestamp | None = None,
    precise_cuts: bool = False,
    cookies_file: CookiesFile = None,
    pace: Pace | str | None = None,
) -> DownloadResult:
    """Download only a video's audio (no video stream).

    Simplest use: ``download_youtube_audio(url)`` → the best audio stream, kept
    in whatever format the source offers (YouTube's is usually Opus in a
    ``.webm`` container), named ``Title (video_id).webm`` in ``~/Downloads``.

    Pass ``audio_format`` to get a specific format instead:

        >>> download_youtube_audio(url, audio_format="mp3")  # doctest: +SKIP

    Args:
        url: The video URL (or id).
        download_dir: Destination directory. Defaults to
            :func:`default_download_dir`.
        audio_format: Target format as an extension (``"mp3"``, ``".wav"``, ...).
            The default ``None`` means **no conversion** — keep the downloaded
            bytes exactly as they came, which needs no ffmpeg and avoids
            re-encoding a lossy stream into another lossy format.
        bitrate: Bitrate for lossy targets (e.g. ``"320k"``). Ignored when
            ``audio_format`` is lossless or ``None``.
        keep_original: When converting, also keep the originally downloaded
            file (by default it is removed once converted).
        on_error: What to do when conversion fails (ffmpeg missing or erroring).
            ``"raise"`` (default) propagates
            :class:`~yb.audio_convert.AudioConversionError`; ``"warn"`` emits a
            warning and returns the unconverted download. Either way the
            downloaded audio is left on disk — a failed conversion never costs
            you the download.
        fmt: yt-dlp format selector (default best audio-only stream).
        filename_template: yt-dlp output template (default
            ``"%(title)s (%(id)s).%(ext)s"``).
        write_info_json: Also save the full metadata as ``*.info.json``.
        write_thumbnail: Also save the thumbnail image.
        write_description: Also save the description as ``*.description``.
        write_subtitles: Also save uploaded subtitles for ``subtitle_langs``.
        write_auto_subtitles: Also save auto-generated subtitles.
        subtitle_langs: Subtitle languages to fetch when subtitles are enabled.
        quiet: Suppress yt-dlp console output.
        extra_opts: Any additional raw yt-dlp options (merged last, so they win).
        pace: As in :func:`download_youtube_video`.
        start, end, precise_cuts: Download only a span, as in
            :func:`download_youtube_video`:

                >>> download_youtube_audio(url, start="0:07.9", end="0:08.75")  # doctest: +SKIP

    Returns:
        A :class:`DownloadResult` whose ``path`` is the audio file — converted
        when ``audio_format`` was given and conversion succeeded.

    Raises:
        ValueError: If ``on_error`` is not ``"raise"`` or ``"warn"``.
        AudioConversionError: If conversion fails and ``on_error="raise"``.
    """
    if on_error not in _ON_CONVERT_ERROR_CHOICES:
        raise ValueError(
            f"on_error must be one of {sorted(_ON_CONVERT_ERROR_CHOICES)}, "
            f"got {on_error!r}"
        )

    result = download_youtube_video(
        url,
        download_dir=download_dir,
        fmt=fmt,
        merge_to=None,  # keep the audio stream's own container
        filename_template=filename_template,
        write_info_json=write_info_json,
        write_thumbnail=write_thumbnail,
        write_description=write_description,
        write_subtitles=write_subtitles,
        write_auto_subtitles=write_auto_subtitles,
        subtitle_langs=subtitle_langs,
        quiet=quiet,
        extra_opts=extra_opts,
        start=start,
        end=end,
        precise_cuts=precise_cuts,
        cookies_file=cookies_file,
        pace=pace,
    )
    if audio_format is None:
        return result

    from yb.audio_convert import AudioConversionError, convert_audio

    original = result.path
    try:
        converted = convert_audio(original, audio_format, bitrate=bitrate)
    except AudioConversionError:
        if on_error == "raise":
            raise
        warnings.warn(
            f"Could not convert to {audio_format!r}; keeping the downloaded "
            f"file as is: {original}",
            stacklevel=2,
        )
        return result

    if converted != original and not keep_original:
        original.unlink(missing_ok=True)
    result.path = converted
    return result


@dataclass(frozen=True)
class SearchHit:
    """One row of :func:`search_youtube` (flat extraction: no per-video fetch).

    ``duration`` is in seconds and may be ``None`` (live streams, some results).
    """

    id: str
    title: str
    duration: float | None
    channel: str | None
    url: str


#: Cap on ``limit`` so a typo does not turn into a thousand-result query.
MAX_SEARCH_LIMIT = 50


def search_youtube(
    query: str,
    *,
    limit: int = 5,
    extra_opts: dict | None = None,
    cookies_file: CookiesFile = None,
) -> list[SearchHit]:
    """Search YouTube by name; returns up to ``limit`` hits, best match first.

    Hand a hit's ``url`` to :func:`download_youtube_audio` /
    :func:`download_youtube_video`:

        >>> hits = search_youtube("हनुमान चालीसा हरिहरन", limit=6)  # doctest: +SKIP
        >>> download_youtube_audio(hits[0].url)  # doctest: +SKIP

    Uses yt-dlp's ``ytsearchN:`` with flat extraction (one request, no per-video
    fetch), sharing the cookie and JS-runtime handling of the downloads.

    Args:
        query: What to search for (any script).
        limit: How many results, 1..:data:`MAX_SEARCH_LIMIT`.
        extra_opts: Additional raw yt-dlp options (merged last).
        cookies_file: See :func:`download_youtube_video`.

    Raises:
        ValueError: If ``query`` is blank or ``limit`` is out of range.
    """
    if not query.strip():
        raise ValueError("query must not be blank")
    if not 1 <= limit <= MAX_SEARCH_LIMIT:
        raise ValueError(f"limit must be in 1..{MAX_SEARCH_LIMIT}, got {limit}")

    info = _extract_info(
        f"ytsearch{limit}:{query}",
        {"quiet": True, "skip_download": True, "extract_flat": True},
        extra_opts=extra_opts,
        cookies_file=cookies_file,
    )
    entries = (info or {}).get("entries") or []
    return [_search_hit(e) for e in entries if e and (e.get("id") or e.get("url"))]


def _search_hit(entry: dict) -> SearchHit:
    video_id = entry.get("id") or ""
    return SearchHit(
        id=video_id,
        title=entry.get("title") or "",
        duration=entry.get("duration"),
        channel=entry.get("channel") or entry.get("uploader"),
        url=entry.get("url") or f"https://www.youtube.com/watch?v={video_id}",
    )


def youtube_playlist_info(
    url: str,
    *,
    playlist_items: str | None = None,
    flat: bool = True,
    extra_opts: dict | None = None,
    cookies_file: CookiesFile = None,
) -> dict[str, Any]:
    """Fetch a playlist's per-video metadata without downloading.

    Returns a dict with playlist-level fields (``playlist_id``, ``playlist_title``,
    ``webpage_url``, ``uploader``, ``count``) and an ``entries`` list. With
    ``flat=True`` (default) extraction is fast/shallow (each entry has at least
    ``id``, ``title``, ``url``); with ``flat=False`` each entry is fully resolved
    and trimmed to :data:`_INFO_FIELDS` (slower, but includes duration/fps/etc.).

    Args:
        url: The playlist URL.
        playlist_items: yt-dlp ``--playlist-items`` selector, 1-based, e.g.
            ``"2:"`` (all but the first), ``"2"`` (only the 2nd), ``"1:5,8"``.
        flat: Shallow vs full per-entry extraction.
        extra_opts: Additional raw yt-dlp options (merged last).
        cookies_file: See :func:`download_youtube_video`.
    """
    opts: dict[str, Any] = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": "in_playlist" if flat else False,
        "ignoreerrors": True,
    }
    if playlist_items:
        opts["playlist_items"] = playlist_items
    info = _extract_info(url, opts, extra_opts=extra_opts, cookies_file=cookies_file)

    raw_entries = (info.get("entries") if info else None) or []
    if flat:
        entries = [
            {
                "id": e.get("id"),
                "title": e.get("title"),
                "webpage_url": e.get("url") or e.get("webpage_url"),
                "duration": e.get("duration"),
            }
            for e in raw_entries
            if e
        ]
    else:
        entries = [_trim_info(e) for e in raw_entries if e]
    return {
        "playlist_id": (info or {}).get("id"),
        "playlist_title": (info or {}).get("title"),
        "webpage_url": (info or {}).get("webpage_url"),
        "uploader": (info or {}).get("uploader"),
        "count": len(entries),
        "entries": entries,
    }


def download_youtube_playlist(
    url: str,
    *,
    download_dir: PathLike | None = None,
    playlist_items: str | None = None,
    skip_first: bool = False,
    title_reject: str | None = None,
    download_archive: PathLike | None = None,
    fmt: str = "bestvideo+bestaudio/best",
    merge_to: str | None = "mp4",
    filename_template: str = DEFAULT_OUTTMPL,
    write_info_json: bool = True,
    write_thumbnail: bool = False,
    write_description: bool = False,
    write_subtitles: bool = False,
    write_auto_subtitles: bool = False,
    subtitle_langs: tuple[str, ...] = ("en",),
    cookies_from_browser: str | tuple | None = None,
    extractor_args: dict | None = None,
    quiet: bool = True,
    extra_opts: dict | None = None,
    cookies_file: CookiesFile = None,
    pace: Pace | str | None = None,
    item_folders: bool = False,
    embed_metadata: bool = False,
) -> list[DownloadResult]:
    """Download all (or a selected subset of) a YouTube playlist's videos.

    Simplest use: ``download_youtube_playlist(url)`` → every video downloaded best
    quality merged to mp4 into ``download_dir`` (default ``~/Downloads``), each with
    its ``*.info.json`` sidecar (``write_info_json`` defaults to ``True`` here, since
    a playlist download is usually an archival operation).

    Selecting a subset (yt-dlp ``--playlist-items`` is **1-based**):

        # skip the first ("PV"/intro) entry, keep the rest
        download_youtube_playlist(url, skip_first=True)         # -> playlist_items="2:"
        download_youtube_playlist(url, playlist_items="2:")     # same, explicit
        download_youtube_playlist(url, playlist_items="2")      # only the 2nd video
        download_youtube_playlist(url, title_reject="PV")       # skip entries whose title contains "PV"

    Args:
        url: The playlist URL.
        download_dir: Destination directory (default :func:`default_download_dir`).
        playlist_items: yt-dlp item selector (1-based; ``"2:"``, ``"2"``, ``"1:5,8"``).
        skip_first: Convenience for ``playlist_items="2:"`` (ignored if
            ``playlist_items`` is given).
        title_reject: Skip entries whose (case-insensitive) title contains this
            substring — more robust than a positional skip if ordering changes.
        download_archive: Path to a yt-dlp archive file recording downloaded ids,
            making re-runs idempotent/resumable.
        fmt: yt-dlp format selector (default best video + best audio).
        merge_to: Container to merge into (default ``"mp4"``; needs ffmpeg).
        filename_template: yt-dlp output template (default
            ``"%(title)s (%(id)s).%(ext)s"``).
        write_info_json: Save each video's ``*.info.json`` (default ``True``).
        write_thumbnail, write_description, write_subtitles, write_auto_subtitles,
        subtitle_langs: As in :func:`download_youtube_video`.
        cookies_from_browser: Browser to read cookies from for bot-detection /
            age / region issues, e.g. ``"safari"`` or ``("chrome", "Profile 1")``.
        extractor_args: yt-dlp ``extractor_args`` (e.g.
            ``{"youtube": {"player_client": ["web_safari"]}}``).
        quiet: Suppress yt-dlp console output.
        extra_opts: Any additional raw yt-dlp options (merged last, so they win).
        cookies_file: As in :func:`download_youtube_video`; an explicit
            ``cookies_from_browser`` takes precedence over the default file.
        pace: Be gentle with YouTube: a :class:`~yb.download.pacing.Pace` or a
            preset name (``"polite"``: sleep 20-60 s between items, 1 s between
            requests, 4 MB/s cap). Default ``None`` adds nothing. Raw yt-dlp
            options in ``extra_opts`` win over it.
        item_folders: Put each item in its own folder ``001_<id>/<id>.<ext>``
            (the number is the 1-based playlist position, stable under
            ``playlist_items``), sidecars beside it under flat id-keyed names.
            Incompatible with a custom ``filename_template``.
        embed_metadata: Write title/artist/etc. into the media file (yt-dlp
            ``--embed-metadata``; needs ffmpeg).

    Audio only: pass ``fmt="bestaudio/best", merge_to=None`` (keeps the source
    stream, e.g. ``.m4a``, without re-encoding).

    Raises:
        RateLimitedError: On HTTP 429 or a "confirm you're not a bot" wall, with
            a backoff hint. (Per-item failures under ``ignoreerrors`` are skipped.)

    Returns:
        A list of :class:`DownloadResult`, one per successfully-downloaded entry,
        in playlist order. Entries skipped by selection/filter or that failed
        (under ``ignoreerrors``) are omitted.
    """
    from yt_dlp import YoutubeDL

    out_dir = Path(download_dir) if download_dir else default_download_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    if playlist_items is None and skip_first:
        playlist_items = "2:"
    if item_folders:
        if filename_template != DEFAULT_OUTTMPL:
            raise ValueError(
                "item_folders=True sets the filename template; "
                "drop filename_template (or drop item_folders)"
            )
        filename_template = ITEM_FOLDER_OUTTMPL

    opts: dict[str, Any] = {
        "format": fmt,
        "outtmpl": str(out_dir / filename_template),
        "noplaylist": False,
        "ignoreerrors": "only_download",
        "quiet": quiet,
        "writeinfojson": write_info_json,
        "writethumbnail": write_thumbnail,
        "writedescription": write_description,
        "writesubtitles": write_subtitles,
        "writeautomaticsub": write_auto_subtitles,
        "subtitleslangs": list(subtitle_langs),
    }
    if merge_to:
        opts["merge_output_format"] = merge_to
    if playlist_items:
        opts["playlist_items"] = playlist_items
    if download_archive:
        opts["download_archive"] = str(Path(download_archive).expanduser())
    if cookies_from_browser:
        opts["cookiesfrombrowser"] = _coerce_cookies_from_browser(cookies_from_browser)
    if extractor_args:
        opts["extractor_args"] = extractor_args
    opts.update(pace_opts(pace))
    if title_reject:
        opts["match_filter"] = _reject_title_filter(title_reject)
    if embed_metadata:
        opts["postprocessors"] = [
            *opts.get("postprocessors", []),
            {"key": "FFmpegMetadata", "add_metadata": True},
        ]

    cookie_opts = _cookie_opts(
        cookies_file, cookies_from_browser=cookies_from_browser, extra_opts=extra_opts
    )
    with _final_opts(opts, cookie_opts, extra_opts) as final:
        with explain_rate_limit(), YoutubeDL(with_runtime_opts(final)) as ydl:
            info = ydl.extract_info(url, download=True)

    results: list[DownloadResult] = []
    for entry in (info.get("entries") if info else None) or []:
        if not entry:
            continue  # selection/filter skipped it, or it failed under ignoreerrors
        path = _resolve_output_path(entry, ydl, out_dir, merge_to)
        sidecars = _collect_sidecars(
            entry,
            path,
            info_json=write_info_json,
            thumbnail=write_thumbnail,
            description=write_description,
            subtitles=write_subtitles or write_auto_subtitles,
        )
        results.append(
            DownloadResult(path=path, info=_trim_info(entry), sidecars=sidecars)
        )
    return results


def _coerce_cookies_from_browser(value: str | tuple) -> tuple:
    """Normalize ``cookies_from_browser`` into yt-dlp's ``cookiesfrombrowser`` tuple."""
    if isinstance(value, str):
        return (value,)
    return tuple(value)


def _reject_title_filter(substring: str):
    """Build a yt-dlp ``match_filter`` that skips entries whose title contains ``substring``."""
    needle = substring.lower()

    def _filter(info_dict, *, incomplete=False):
        title = (info_dict.get("title") or "").lower()
        if needle in title:
            return f"skipping {info_dict.get('title')!r}: title matches reject {substring!r}"
        return None

    return _filter


def _resolve_output_path(info, ydl, out_dir: Path, merge_to: str | None) -> Path:
    """Best-effort resolution of the final media path yt-dlp produced."""
    downloads = info.get("requested_downloads")
    if downloads and downloads[0].get("filepath"):
        return Path(downloads[0]["filepath"])
    name = ydl.prepare_filename(info)
    p = Path(name)
    if merge_to and p.suffix.lower() != f".{merge_to.lower()}":
        merged = p.with_suffix(f".{merge_to}")
        if merged.exists():
            return merged
    return p


def _collect_sidecars(
    info,
    media_path: Path,
    *,
    info_json: bool,
    thumbnail: bool,
    description: bool,
    subtitles: bool,
) -> dict[str, Any]:
    stem = media_path.with_suffix("")

    def sibling(ext: str) -> Path:
        # Not ``stem.with_suffix``: a dot in the name ("... [7.9-8.75]") is not an extension.
        return stem.with_name(stem.name + ext)

    out: dict[str, Any] = {}
    if info_json:
        cand = sibling(".info.json")
        if cand.exists():
            out["info_json"] = cand
    if description:
        cand = sibling(".description")
        if cand.exists():
            out["description"] = cand
    if thumbnail:
        for ext in (".jpg", ".webp", ".png"):
            cand = sibling(ext)
            if cand.exists():
                out["thumbnail"] = cand
                break
    if subtitles:
        subs = sorted(
            media_path.parent.glob(f"{glob_escape(stem.name)}.*.srt")
        ) + sorted(media_path.parent.glob(f"{glob_escape(stem.name)}.*.vtt"))
        if subs:
            out["subtitles"] = subs
    return out


def glob_escape(name: str) -> str:
    """Escape glob metacharacters in a literal filename stem."""
    return (
        name.replace("[", "[[]")
        .replace("]", "[]]")
        .replace("*", "[*]")
        .replace("?", "[?]")
    )


def _trim_info(info: dict | None) -> dict[str, Any]:
    if not info:
        return {}
    return {k: info.get(k) for k in _INFO_FIELDS if info.get(k) is not None}

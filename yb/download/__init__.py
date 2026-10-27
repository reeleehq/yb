"""Media download (yt-dlp) — fetch videos, audio, and their metadata.

A separate, optionally-installed module (``pip install 'yb[download]'``).
Common use:

    >>> from yb.download import download_youtube_video  # doctest: +SKIP
    >>> result = download_youtube_video("https://youtu.be/PRa9ciOe-us")  # doctest: +SKIP
    >>> print(result.path, result.video_id)  # doctest: +SKIP

For audio only — e.g. to feed a transcription or podcast workflow — use
:func:`download_youtube_audio`, which keeps the source format by default and
converts only when you ask it to (conversion needs ffmpeg):

    >>> from yb.download import download_youtube_audio  # doctest: +SKIP
    >>> ep = download_youtube_audio(url, audio_format="mp3")  # doctest: +SKIP

For sound or clip sourcing, fetch just a span (seconds or ``"mm:ss"``; needs
ffmpeg, see :mod:`yb.download.ranges`). The span is recorded in
``result.info["download_range"]`` for provenance:

    >>> clip = download_youtube_audio(url, start="0:07.9", end="0:08.75")  # doctest: +SKIP

To go from a name to a download, search first (:func:`search_youtube`):

    >>> from yb.download import search_youtube  # doctest: +SKIP
    >>> hits = search_youtube("hanuman chalisa", limit=3)  # doctest: +SKIP
    >>> download_youtube_audio(hits[0].url)  # doctest: +SKIP

A service turning user-supplied links into audio uses
:func:`download_audio_bounded`: duration and size caps, mp3 output, and a
copyright notice, with the caps immune to caller ``extra_opts``.

YouTube downloads need a JavaScript runtime (Deno) and yt-dlp's solver
scripts; :func:`check_requirements` (or ``yb check``) says what's missing and
how to install it. The first download in a process runs it and warns.
"""

from yb.audio_convert import AudioConversionError, convert_audio
from yb.download.youtube import (
    download_youtube_video,
    download_youtube_audio,
    youtube_video_info,
    download_youtube_playlist,
    youtube_playlist_info,
    search_youtube,
    SearchHit,
    default_download_dir,
    DownloadResult,
    DOWNLOAD_DIR_ENV,
    DEFAULT_OUTTMPL,
    DEFAULT_AUDIO_FMT,
)
from yb.download.pacing import Pace, PACE_PRESETS, RateLimitedError
from yb.download.bounded import (
    download_audio_bounded,
    AudioDownload,
    AudioLimitError,
    require_http_url,
    COPYRIGHT_NOTICE,
)
from yb.download.ranges import TimeRange, parse_timestamp
from yb.download.requirements import (
    check_requirements,
    find_js_runtime,
    DownloadRequirementWarning,
    JsRuntime,
)

__all__ = [
    "download_youtube_video",
    "download_youtube_audio",
    "youtube_video_info",
    "download_youtube_playlist",
    "youtube_playlist_info",
    "search_youtube",
    "download_audio_bounded",
    "AudioDownload",
    "AudioLimitError",
    "require_http_url",
    "COPYRIGHT_NOTICE",
    "SearchHit",
    "default_download_dir",
    "convert_audio",
    "AudioConversionError",
    "DownloadResult",
    "DOWNLOAD_DIR_ENV",
    "DEFAULT_OUTTMPL",
    "DEFAULT_AUDIO_FMT",
    "check_requirements",
    "find_js_runtime",
    "DownloadRequirementWarning",
    "JsRuntime",
    "Pace",
    "PACE_PRESETS",
    "RateLimitedError",
    "TimeRange",
    "parse_timestamp",
]

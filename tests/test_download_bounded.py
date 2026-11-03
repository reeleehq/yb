"""``download_audio_bounded``: the policy, with yt-dlp calls faked (no network)."""

import functools
import itertools
import http.server
import threading
import types
from pathlib import Path

import pytest

pytest.importorskip("yt_dlp")  # the pinned match_filter is built by yt-dlp

from yb.download import (  # noqa: E402
    AudioLimitError,
    AudioSourceError,
    AudioTargetError,
    COPYRIGHT_NOTICE,
    RateLimitedError,
    download_audio_bounded,
    require_http_url,
)
from yb.download import bounded  # noqa: E402
from yb.download import youtube as ytdl  # noqa: E402


@pytest.fixture
def fakes(monkeypatch, tmp_path):
    """Fake ``yt_dlp.YoutubeDL``; record its options and every request it makes."""
    seen = {
        "opts": None,
        "requests": [],
        "redirects": {},  # requested URL -> URL the response ends at
        "media_urls": ["https://cdn.example.com/a.webm"],
        "progress": [10],  # downloaded_bytes reported to the progress hooks
        "size": 10,
        "write": True,
        "preview_info": {"duration": 60},
        "downloads": 0,
        "raise": None,  # an exception the download raises, after writing a .part
    }

    class FakeYDL:
        def __init__(self, opts):
            seen["opts"] = self.params = opts

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def urlopen(self, req):
            seen["requests"].append(req)
            return types.SimpleNamespace(
                url=seen["redirects"].get(req, req), close=lambda: None
            )

        def extract_info(self, url, *, download):
            assert download is False
            self.urlopen(url)
            return dict(seen["preview_info"])

        def process_ie_result(self, info, *, download):
            seen["downloads"] += 1
            for media in seen["media_urls"]:
                self.urlopen(media)
            for hook in self.params["progress_hooks"]:
                for n in seen["progress"]:
                    hook({"downloaded_bytes": n})
            work = Path(self.params["outtmpl"]).parent
            if seen["raise"]:
                (work / "x.part").write_bytes(b"1")
                raise seen["raise"]
            if seen["write"]:
                (work / "Song (id).mp3").write_bytes(b"x" * seen["size"])
            return {
                **info,
                "id": "id",
                "title": "Song",
                "duration": 60,
                "requested_downloads": [{"filepath": str(work / "Song (id).webm")}],
            }

    monkeypatch.setattr(bounded, "youtube_dl_cls", lambda: FakeYDL)
    monkeypatch.setattr(ytdl, "with_runtime_opts", lambda opts: opts)
    return seen


def run(tmp_path, **kw):
    return download_audio_bounded("https://example.com/v", download_dir=tmp_path, **kw)


def leftovers(tmp_path):
    return sorted(p.name for p in tmp_path.iterdir())


def test_happy_path_moves_mp3_into_download_dir(fakes, tmp_path):
    got = run(tmp_path, max_bytes=100, max_duration_s=120)
    assert got.path.name == "Song (id).mp3" and got.path.exists()
    assert got.path.parent.parent == tmp_path  # its own per-call directory
    assert (got.title, got.duration_s, got.notice) == ("Song", 60, COPYRIGHT_NOTICE)
    assert [p.name for p in got.path.parent.iterdir()] == ["Song (id).mp3"]


def test_two_calls_on_one_video_do_not_collide(fakes, tmp_path):
    first, second = run(tmp_path), run(tmp_path)
    assert first.path != second.path and first.path.exists() and second.path.exists()


def test_validator_runs_before_any_network(fakes, tmp_path):
    def refuse(url):
        raise ValueError("no")

    with pytest.raises(ValueError, match="no"):
        run(tmp_path, validate_target=refuse)
    assert fakes["opts"] is None and not fakes["requests"]


def _refuse_metadata_host(url):
    if "169.254.169.254" in url:
        raise ValueError("private")


def test_every_request_is_validated_not_only_the_link(fakes, tmp_path):
    """The media URL a page points at is checked before it is fetched."""
    fakes["media_urls"] = ["http://169.254.169.254/latest/meta-data"]
    seen = []

    def validate(url):
        seen.append(url)
        _refuse_metadata_host(url)

    with pytest.raises(ValueError, match="private"):
        run(tmp_path, validate_target=validate)
    assert "http://169.254.169.254/latest/meta-data" in seen
    assert fakes["requests"] == ["https://example.com/v"]  # the media was never sent
    assert leftovers(tmp_path) == []


def test_a_redirect_into_a_refused_host_is_refused(fakes, tmp_path):
    media = fakes["media_urls"][0]
    fakes["redirects"][media] = "http://169.254.169.254/x"
    with pytest.raises(ValueError, match="private"):
        run(tmp_path, validate_target=_refuse_metadata_host)
    assert leftovers(tmp_path) == []


def test_unknown_size_stream_is_cut_at_max_bytes(fakes, tmp_path):
    fakes["progress"] = [50, 100, 101]
    with pytest.raises(AudioLimitError, match="100-byte"):
        run(tmp_path, max_bytes=100)
    assert leftovers(tmp_path) == []


def test_wall_clock_deadline_aborts(fakes, tmp_path, monkeypatch):
    ticks = itertools.chain([0.0, 0.0, 5.0], itertools.repeat(11.0))
    monkeypatch.setattr(
        bounded, "time", types.SimpleNamespace(monotonic=lambda: next(ticks))
    )
    with pytest.raises(AudioLimitError, match="time limit"):
        run(tmp_path, timeout_s=10)
    assert leftovers(tmp_path) == []


@pytest.mark.parametrize(
    "message,expected",
    [
        ("ERROR: Unsupported URL: https://example.com/v", AudioSourceError),
        ("ERROR: HTTP Error 429: Too Many Requests", RateLimitedError),
    ],
)
def test_ytdlp_errors_are_typed(fakes, tmp_path, message, expected):
    from yt_dlp.utils import DownloadError

    fakes["raise"] = DownloadError(message)
    with pytest.raises(expected):
        run(tmp_path)
    assert leftovers(tmp_path) == []


def test_source_errors_are_value_errors():
    assert issubclass(AudioSourceError, ValueError)


def test_a_refusal_is_an_audio_target_error(fakes, tmp_path):
    def refuse(url):
        raise ValueError("no")

    with pytest.raises(AudioTargetError, match="no"):
        run(tmp_path, validate_target=refuse)


def test_an_extractor_value_error_is_a_source_error_not_unwrapped(fakes, tmp_path):
    """yt-dlp records the cause of e.g. a malformed page's JSON; it is not ours."""
    import json

    from yt_dlp.utils import DownloadError

    try:
        json.loads("{")
    except ValueError as exc:
        cause = exc
    fakes["raise"] = DownloadError("bad page", exc_info=(type(cause), cause, None))
    with pytest.raises(AudioSourceError, match="bad page"):
        run(tmp_path)


def test_a_logger_is_a_deployment_option(fakes, tmp_path):
    log = object()
    run(tmp_path, extra_opts={"logger": log})
    assert fakes["opts"]["logger"] is log


def test_a_refusal_wrapped_by_ytdlp_is_unwrapped(fakes, tmp_path):
    from yt_dlp.utils import DownloadError

    refusal = AudioLimitError("download exceeds the 1-byte limit")
    fakes["raise"] = DownloadError("wrapped", exc_info=(type(refusal), refusal, None))
    with pytest.raises(AudioLimitError) as got:
        run(tmp_path)
    assert got.value is refusal


def test_no_ytdlp_is_an_import_error_with_the_hint(monkeypatch, tmp_path):
    import sys

    monkeypatch.setitem(sys.modules, "yt_dlp", None)
    with pytest.raises(ImportError, match=r"pip install 'yb\[download\]'"):
        run(tmp_path)
    assert leftovers(tmp_path) == []


def test_no_ambient_cookies_by_default(fakes, tmp_path, monkeypatch):
    jar = tmp_path / "jar.txt"
    jar.write_text("# Netscape HTTP Cookie File\n")
    monkeypatch.setenv(ytdl.COOKIES_FILE_ENV, str(jar))
    run(tmp_path / "a")
    assert "cookiefile" not in fakes["opts"]
    run(tmp_path / "b", cookies_file=jar)
    assert fakes["opts"]["cookiefile"] == str(jar)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://h/x", "https://"])
def test_default_validator_floor(url):
    with pytest.raises(ValueError):
        require_http_url(url)


@pytest.mark.parametrize(
    "info,match",
    [
        ({"duration": 3601}, "3601s"),
        ({"_type": "playlist", "entries": [{}]}, "playlists"),
        ({"entries": [{}]}, "playlists"),
        ({"is_live": True}, "live"),
        ({"live_status": "is_upcoming"}, "live"),
    ],
)
def test_refused_from_metadata_before_downloading(fakes, tmp_path, info, match):
    fakes["preview_info"] = info
    with pytest.raises(AudioLimitError, match=match):
        run(tmp_path, max_duration_s=3600)
    assert fakes["downloads"] == 0


def test_unknown_duration_passes_the_duration_check(fakes, tmp_path):
    fakes["preview_info"] = {}
    assert run(tmp_path).path.exists()


def test_oversized_output_is_refused_and_nothing_is_left(fakes, tmp_path):
    fakes["size"] = 101
    with pytest.raises(AudioLimitError, match="100-byte"):
        run(tmp_path, max_bytes=100)
    assert leftovers(tmp_path) == []


def test_no_output_is_refused_and_nothing_is_left(fakes, tmp_path):
    fakes["write"] = False
    with pytest.raises(AudioLimitError, match="no audio"):
        run(tmp_path)
    assert leftovers(tmp_path) == []


def test_download_failure_cleans_the_work_dir(fakes, tmp_path):
    fakes["raise"] = RuntimeError("net")
    with pytest.raises(RuntimeError):
        run(tmp_path)
    assert leftovers(tmp_path) == []


def test_pinned_opts_are_single_bounded_nonlive_mp3(fakes, tmp_path):
    run(tmp_path, max_bytes=100, extra_opts={"http_headers": {"X": "1"}})
    opts = fakes["opts"]
    assert opts["max_filesize"] == 100 and opts["progress_hooks"]
    assert "rtmp" not in opts["format"] and "protocol~=" in opts["format"]
    assert opts["external_downloader_args"]["ffmpeg_i"] == [
        "-protocol_whitelist",
        "file",
    ]
    # max_downloads would make yt-dlp raise after the first success.
    assert opts["noplaylist"] and "max_downloads" not in opts
    assert opts["playlist_items"] == "1" and opts["keepvideo"] is False
    assert opts["postprocessors"][0]["preferredcodec"] == "mp3"
    assert opts["http_headers"] == {"X": "1"}  # deployment options pass through
    assert "match_filter" not in opts  # _check_preview is the one duration check
    assert opts["no_warnings"] and "m3u8'" not in opts["format"].replace(
        "m3u8_native", ""
    )


@pytest.mark.parametrize(
    "key", ["max_filesize", "outtmpl", "noplaylist", "format", "match_filter", "paths"]
)
def test_extra_opts_outside_the_allowlist_raise(fakes, tmp_path, key):
    with pytest.raises(ValueError, match=key):
        run(tmp_path, extra_opts={key: 1})
    assert fakes["opts"] is None


@pytest.mark.parametrize(
    "kw", [{"max_bytes": 0}, {"max_duration_s": -1}, {"timeout_s": 0}]
)
def test_caps_must_be_positive(fakes, tmp_path, kw):
    with pytest.raises(ValueError):
        run(tmp_path, **kw)


def test_real_ytdlp_downloads_a_local_file_as_mp3(tmp_path, monkeypatch):
    """No fakes: real yt-dlp (generic extractor) + ffmpeg against a local HTTP server."""
    import functools
    import http.server
    import shutil
    import subprocess
    import threading

    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg is not installed")
    served = tmp_path / "srv"
    served.mkdir()
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=duration=1", str(served / "a.mp3")],
        capture_output=True,
        check=True,
    )
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(served)
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        got = download_audio_bounded(
            f"http://127.0.0.1:{server.server_port}/a.mp3",
            download_dir=tmp_path / "out",
            max_bytes=10**6,
            max_duration_s=60,
        )
    finally:
        server.shutdown()
    assert got.path.suffix == ".mp3" and got.path.stat().st_size > 0


class _Hostile(http.server.BaseHTTPRequestHandler):
    """A page embedding a loopback media URL, a redirect into it, endless streams."""

    protocol_version = "HTTP/1.1"
    port = 0

    def log_message(self, *args):
        pass

    def _send(self, body: bytes, ctype: str):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        secret = f"http://127.0.0.1:{self.port}/secret.mp3"
        if self.path == "/page.html":
            self._send(
                f'<html><audio src="{secret}"></audio></html>'.encode(), "text/html"
            )
        elif self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", secret)
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif self.path in ("/endless.mp3", "/slow.mp3"):
            self.send_response(200)
            self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            chunk = b"\xff" * 4096
            try:
                while True:
                    self.wfile.write(b"%x\r\n%s\r\n" % (len(chunk), chunk))
                    self.wfile.flush()
                    if self.path == "/slow.mp3":
                        threading.Event().wait(0.1)
            except OSError:
                pass  # the client hung up, as it should
        elif self.path == "/secret.mp3":
            self._send(b"\xff" * 100, "audio/mpeg")
        else:
            self._send(b"<html>nothing to see</html>", "text/html")


@pytest.fixture
def hostile():
    """Base URL of a :class:`_Hostile` server, reached as ``localhost``."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Hostile)
    _Hostile.port = server.server_port
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://localhost:{server.server_port}"
    server.shutdown()


def _no_ip_literal_loopback(url):
    from urllib.parse import urlparse

    if urlparse(url).hostname == "127.0.0.1":
        raise ValueError(f"refused {url}")


@pytest.mark.parametrize("path", ["/page.html", "/redirect"])
def test_real_ytdlp_never_hands_back_a_refused_host(hostile, tmp_path, path):
    with pytest.raises(ValueError, match="refused http://127.0.0.1"):
        download_audio_bounded(
            hostile + path,
            download_dir=tmp_path,
            validate_target=_no_ip_literal_loopback,
        )
    assert leftovers(tmp_path) == []


def test_real_ytdlp_cuts_an_endless_stream_at_max_bytes(hostile, tmp_path):
    with pytest.raises(AudioLimitError, match="100000-byte"):
        download_audio_bounded(
            hostile + "/endless.mp3", download_dir=tmp_path, max_bytes=100_000
        )
    assert leftovers(tmp_path) == []


def test_real_ytdlp_stops_a_trickle_at_the_deadline(hostile, tmp_path):
    with pytest.raises(AudioLimitError, match="time limit"):
        download_audio_bounded(
            hostile + "/slow.mp3", download_dir=tmp_path, timeout_s=0.5
        )
    assert leftovers(tmp_path) == []


def test_real_ytdlp_unsupported_page_is_an_audio_source_error(hostile, tmp_path):
    with pytest.raises(AudioSourceError, match="Unsupported URL"):
        download_audio_bounded(hostile + "/nothing", download_dir=tmp_path)
    assert leftovers(tmp_path) == []


def test_ffmpeg_fallback_may_only_read_local_files():
    """HLS delegated to ffmpeg must not fetch segments behind the request guard."""
    from yt_dlp import YoutubeDL
    from yt_dlp.downloader.external import FFmpegFD

    opts = bounded._pinned_opts(Path("w"), max_bytes=1, deadline=0.0)
    ydl = YoutubeDL({"external_downloader_args": opts["external_downloader_args"]})
    fd = FFmpegFD(ydl, ydl.params)
    assert fd._configuration_args(("_i1", "_i")) == ["-protocol_whitelist", "file"]


def test_real_ytdlp_bounds_a_fragmented_hls_source(tmp_path):
    """HLS (native, fragment by fragment): every fragment URL is checked, the byte
    cap holds across fragments, and a source under the caps comes out as mp3."""
    import shutil
    import subprocess

    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg is not installed")
    served = tmp_path / "srv"
    served.mkdir()
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=duration=6",
            "-c:a",
            "aac",
            "-f",
            "hls",
            "-hls_time",
            "1",
            "-hls_list_size",
            "0",
            "-hls_segment_filename",
            str(served / "seg%03d.ts"),
            str(served / "a.m3u8"),
        ],
        capture_output=True,
        check=True,
    )
    segments = sorted(served.glob("seg*.ts"))
    total = sum(p.stat().st_size for p in segments)
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(served)
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/a.m3u8"
    seen = []
    try:
        with pytest.raises(AudioLimitError, match="byte limit"):
            download_audio_bounded(
                url, download_dir=tmp_path / "capped", max_bytes=total // 3
            )
        assert leftovers(tmp_path / "capped") == []
        got = download_audio_bounded(
            url, download_dir=tmp_path / "ok", validate_target=seen.append
        )
    finally:
        server.shutdown()
    assert got.path.suffix == ".mp3" and got.path.stat().st_size > 0
    assert {p.name for p in segments} <= {u.rsplit("/", 1)[-1] for u in seen}

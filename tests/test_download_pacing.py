"""Offline tests for pacing, item folders and rate-limit errors (yt-dlp is faked)."""

import sys
import types

import pytest

from yb.download import RateLimitedError, download_youtube_audio
from yb.download import download_youtube_playlist, download_youtube_video
from yb.download import requirements as req
from yb.download.pacing import Pace, pace_opts, parse_rate


class _FakeYDL:
    seen: list = []
    error: Exception | None = None

    def __init__(self, opts):
        type(self).seen.append(opts)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        if self.error:
            raise self.error
        if "list" in url:
            return {"id": "pl", "entries": []}
        return {"id": "abc", "title": "T"}

    def prepare_filename(self, info):
        return "/dl/T (abc).mp4"


@pytest.fixture
def ydl(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=_FakeYDL))
    monkeypatch.setattr(req, "check_requirements", lambda **k: [])
    monkeypatch.setattr(req, "find_js_runtime", lambda: None)
    req._preflight_opts.cache_clear()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.delenv("YB_COOKIES_FILE", raising=False)
    _FakeYDL.seen, _FakeYDL.error = [], None
    yield _FakeYDL
    req._preflight_opts.cache_clear()


def test_pace_opts():
    assert pace_opts(None) == {}
    assert pace_opts("polite") == {
        "sleep_interval": 20,
        "max_sleep_interval": 60,
        "sleep_interval_requests": 1,
        "ratelimit": 4 * 1024**2,
    }
    assert pace_opts(Pace(sleep_interval=3)) == {"sleep_interval": 3}
    with pytest.raises(ValueError):
        pace_opts("nope")
    assert parse_rate("500K") == 500 * 1024


def test_default_adds_no_pacing(ydl, tmp_path):
    download_youtube_playlist("list", download_dir=tmp_path)
    opts = ydl.seen[-1]
    assert not {"sleep_interval", "ratelimit", "sleep_interval_requests"} & set(opts)


def test_playlist_polite_audio_archive_items(ydl, tmp_path):
    download_youtube_playlist(
        "list",
        download_dir=tmp_path,
        pace="polite",
        fmt="bestaudio/best",
        merge_to=None,
        download_archive=tmp_path / "archive.txt",
        playlist_items="1-42",
        item_folders=True,
        embed_metadata=True,
        write_description=True,
        write_thumbnail=True,
        write_subtitles=True,
    )
    o = ydl.seen[-1]
    assert o["sleep_interval"] == 20 and o["max_sleep_interval"] == 60
    assert o["sleep_interval_requests"] == 1 and o["ratelimit"] == 4 * 1024**2
    assert o["playlist_items"] == "1-42"
    assert o["download_archive"] == str(tmp_path / "archive.txt")
    assert o["format"] == "bestaudio/best" and "merge_output_format" not in o
    assert o["outtmpl"].endswith("%(playlist_index)03d_%(id)s/%(id)s.%(ext)s")
    assert {"key": "FFmpegMetadata", "add_metadata": True} in o["postprocessors"]
    assert o["writeinfojson"] and o["writedescription"] and o["writethumbnail"]


def test_extra_opts_beat_pace(ydl, tmp_path):
    download_youtube_playlist(
        "list", download_dir=tmp_path, pace="polite", extra_opts={"sleep_interval": 1}
    )
    assert ydl.seen[-1]["sleep_interval"] == 1


def test_item_folders_conflicts_with_custom_template(ydl, tmp_path):
    with pytest.raises(ValueError, match="item_folders"):
        download_youtube_playlist(
            "list", download_dir=tmp_path, item_folders=True, filename_template="x.%(ext)s"
        )


@pytest.mark.parametrize("fn", [download_youtube_video, download_youtube_audio])
def test_video_and_audio_accept_pace(ydl, tmp_path, fn):
    fn("u", download_dir=tmp_path, pace="polite")
    assert ydl.seen[-1]["sleep_interval"] == 20


@pytest.mark.parametrize(
    "message",
    ["HTTP Error 429: Too Many Requests", "Sign in to confirm you're not a bot"],
)
def test_block_becomes_rate_limited_error(ydl, tmp_path, message):
    ydl.error = RuntimeError(message)
    with pytest.raises(RateLimitedError, match="Back off"):
        download_youtube_playlist("list", download_dir=tmp_path)
    with pytest.raises(RateLimitedError):
        download_youtube_video("u", download_dir=tmp_path)


def test_other_errors_pass_through(ydl, tmp_path):
    ydl.error = RuntimeError("Video unavailable")
    with pytest.raises(RuntimeError, match="unavailable") as ei:
        download_youtube_video("u", download_dir=tmp_path)
    assert not isinstance(ei.value, RateLimitedError)

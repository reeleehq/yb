"""Downloading a time range: parsing, the yt-dlp options built, the recorded span.

Offline: yt-dlp is replaced by a recorder, so these assert on the options yb
hands it (the issue's "test against the yt-dlp options built"). One test also
runs yt-dlp's real ``download_range_func`` when yt-dlp is installed.
"""

import math
import sys
import types

import pytest

from yb.download import download_youtube_audio, download_youtube_video
from yb.download import ranges as rng
from yb.download import requirements as req
from yb.download import youtube as ytdl


# ---- parse_timestamp ------------------------------------------------------


@pytest.mark.parametrize(
    "given,seconds",
    [
        (0, 0.0),
        (7.9, 7.9),
        ("7.9", 7.9),
        ("90", 90.0),
        ("1:30", 90.0),
        ("0:07.9", 7.9),
        ("01:02:03", 3723.0),
        ("90:00", 5400.0),
        (" 1:05 ", 65.0),
    ],
)
def test_parse_timestamp(given, seconds):
    assert rng.parse_timestamp(given) == pytest.approx(seconds)


@pytest.mark.parametrize(
    "bad",
    [-1, "-5", "1:-5", "abc", "", "1:2:3:4", "1::2", True, None, [1], math.inf, math.nan],
)
def test_parse_timestamp_rejects_nonsense(bad):
    with pytest.raises(ValueError):
        rng.parse_timestamp(bad)


# ---- TimeRange ------------------------------------------------------------


def test_no_bounds_is_no_range():
    assert rng.TimeRange.of() is None


def test_open_ended_ranges():
    assert rng.TimeRange.of(start=30) == rng.TimeRange(30.0, None)
    assert rng.TimeRange.of(end="0:10") == rng.TimeRange(0.0, 10.0)
    assert rng.TimeRange.of(start=0, end=5) == rng.TimeRange(0.0, 5.0)


@pytest.mark.parametrize("start,end", [(10, 10), (10, 5), ("1:00", 59)])
def test_end_must_follow_start(start, end):
    with pytest.raises(ValueError, match="after start"):
        rng.TimeRange.of(start=start, end=end)


def test_label_is_filename_safe_and_compact():
    assert rng.TimeRange.of(start="0:07.9", end=8.75).label == "7.9-8.75"
    assert rng.TimeRange.of(start=30).label == "30-end"
    assert rng.TimeRange.of(end=2).label == "0-2"


def test_filename_template_gets_the_range_before_the_extension():
    tr = rng.TimeRange.of(start=1, end=2)
    assert (
        rng.ranged_filename_template(ytdl.DEFAULT_OUTTMPL, tr)
        == "%(title)s (%(id)s) [1-2].%(ext)s"
    )
    assert rng.ranged_filename_template("fixed.mp4", tr) == "fixed.mp4"


# ---- the options handed to yt-dlp ------------------------------------------


def _fake_range_func(chapters, ranges):
    return ("RANGES", chapters, ranges)


def test_range_opts_map_to_download_ranges():
    tr = rng.TimeRange.of(start="0:07.9", end=8.75)
    opts = rng.range_opts(tr, range_func=_fake_range_func)
    assert opts == {"download_ranges": ("RANGES", None, [(7.9, 8.75)])}


def test_open_end_is_infinite_and_precise_cuts_force_keyframes():
    opts = rng.range_opts(
        rng.TimeRange.of(start=30), precise_cuts=True, range_func=_fake_range_func
    )
    assert opts["download_ranges"][2] == [(30.0, math.inf)]
    assert opts["force_keyframes_at_cuts"] is True


def test_real_yt_dlp_range_func_yields_the_section():
    pytest.importorskip("yt_dlp")
    opts = rng.range_opts(rng.TimeRange.of(start=1, end=2.5))
    sections = list(opts["download_ranges"]({"id": "x"}, None))
    assert sections == [{"start_time": 1.0, "end_time": 2.5}]


# ---- through the download functions ----------------------------------------


class _FakeYDL:
    seen: list = []

    def __init__(self, opts):
        type(self).seen.append(opts)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        return {"id": "abc", "title": "T", "duration": 99}

    def prepare_filename(self, info):
        return "/dl/T (abc).mp4"


@pytest.fixture
def fake_yt_dlp(monkeypatch):
    utils = types.SimpleNamespace(download_range_func=_fake_range_func)
    mod = types.SimpleNamespace(YoutubeDL=_FakeYDL, utils=utils)
    monkeypatch.setitem(sys.modules, "yt_dlp", mod)
    monkeypatch.setitem(sys.modules, "yt_dlp.utils", utils)
    monkeypatch.setattr(req, "check_requirements", lambda **k: [])
    monkeypatch.setattr(req, "find_js_runtime", lambda: None)
    req._preflight_opts.cache_clear()
    _FakeYDL.seen = []
    yield _FakeYDL
    req._preflight_opts.cache_clear()


def test_no_range_changes_nothing(fake_yt_dlp, tmp_path):
    result = download_youtube_video("u", download_dir=tmp_path)
    opts = fake_yt_dlp.seen[-1]
    assert "download_ranges" not in opts and "force_keyframes_at_cuts" not in opts
    assert opts["outtmpl"] == str(tmp_path / ytdl.DEFAULT_OUTTMPL)
    assert "download_range" not in result.info


def test_video_range_reaches_yt_dlp_and_the_info(fake_yt_dlp, tmp_path):
    result = download_youtube_video(
        "u", download_dir=tmp_path, start="0:07.9", end=8.75
    )
    opts = fake_yt_dlp.seen[-1]
    assert opts["download_ranges"] == ("RANGES", None, [(7.9, 8.75)])
    assert opts["outtmpl"] == str(tmp_path / "%(title)s (%(id)s) [7.9-8.75].%(ext)s")
    assert result.info["download_range"] == {"start": 7.9, "end": 8.75}


def test_a_custom_template_is_left_alone(fake_yt_dlp, tmp_path):
    download_youtube_video(
        "u", download_dir=tmp_path, start=1, filename_template="mine.%(ext)s"
    )
    assert fake_yt_dlp.seen[-1]["outtmpl"] == str(tmp_path / "mine.%(ext)s")


def test_extra_opts_still_win_over_the_range(fake_yt_dlp, tmp_path):
    download_youtube_video(
        "u", download_dir=tmp_path, start=1, extra_opts={"download_ranges": "mine"}
    )
    assert fake_yt_dlp.seen[-1]["download_ranges"] == "mine"


def test_audio_passes_the_range_through(fake_yt_dlp, tmp_path):
    result = download_youtube_audio(
        "u", download_dir=tmp_path, start=5, precise_cuts=True
    )
    opts = fake_yt_dlp.seen[-1]
    assert opts["download_ranges"][2] == [(5.0, math.inf)]
    assert opts["force_keyframes_at_cuts"] is True
    assert result.info["download_range"] == {"start": 5.0, "end": None}


def test_bad_range_fails_before_anything_is_written(fake_yt_dlp, tmp_path):
    target = tmp_path / "never"
    with pytest.raises(ValueError, match="after start"):
        download_youtube_video("u", download_dir=target, start=9, end=3)
    with pytest.raises(ValueError, match="precise_cuts"):
        download_youtube_video("u", download_dir=target, precise_cuts=True)
    assert not target.exists() and fake_yt_dlp.seen == []

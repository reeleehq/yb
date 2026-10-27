"""``download_audio_bounded``: the policy, with yt-dlp calls faked (no network)."""

import pytest

from yb.download import (
    AudioLimitError,
    COPYRIGHT_NOTICE,
    download_audio_bounded,
    require_http_url,
)
from yb.download import bounded
from yb.download.youtube import DownloadResult


@pytest.fixture
def fakes(monkeypatch, tmp_path):
    """Fake the metadata fetch and the download; record what they were given."""
    seen = {"preview": [], "download": [], "size": 10, "preview_info": {"duration": 60}}

    def info(url, **kw):
        seen["preview"].append((url, kw))
        return seen["preview_info"]

    def download(url, **kw):
        seen["download"].append((url, kw))
        original = tmp_path / "Song (id).webm"
        mp3 = tmp_path / "Song (id).mp3"
        mp3.write_bytes(b"x" * seen["size"])
        return DownloadResult(
            path=original, info={"id": "id", "title": "Song", "duration": 60}
        )

    monkeypatch.setattr(bounded, "youtube_video_info", info)
    monkeypatch.setattr(bounded, "download_youtube_video", download)
    return seen


def run(tmp_path, **kw):
    return download_audio_bounded("https://example.com/v", download_dir=tmp_path, **kw)


def test_happy_path_returns_mp3_title_duration_notice(fakes, tmp_path):
    got = run(tmp_path, max_bytes=100, max_duration_s=120)
    assert got.path == tmp_path / "Song (id).mp3" and got.path.exists()
    assert (got.title, got.duration_s, got.notice) == ("Song", 60, COPYRIGHT_NOTICE)


def test_validator_runs_before_any_network(fakes, tmp_path):
    def refuse(url):
        raise ValueError("no")

    with pytest.raises(ValueError, match="no"):
        run(tmp_path, validate_target=refuse)
    assert not fakes["preview"] and not fakes["download"]


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://h/x", "https://"])
def test_default_validator_floor(url):
    with pytest.raises(ValueError):
        require_http_url(url)


def test_too_long_is_refused_before_downloading(fakes, tmp_path):
    fakes["preview_info"] = {"duration": 3601}
    with pytest.raises(AudioLimitError, match="3601s"):
        run(tmp_path, max_duration_s=3600)
    assert not fakes["download"]


def test_unknown_duration_passes_the_duration_check(fakes, tmp_path):
    fakes["preview_info"] = {}
    assert run(tmp_path).path.exists()


def test_oversized_output_is_deleted_and_refused(fakes, tmp_path):
    fakes["size"] = 101
    with pytest.raises(AudioLimitError, match="100-byte"):
        run(tmp_path, max_bytes=100)
    assert not (tmp_path / "Song (id).mp3").exists()


def test_extra_opts_cannot_widen_the_caps(fakes, tmp_path):
    hostile = {
        "max_filesize": 10**12,
        "postprocessors": [],
        "http_headers": {"X": "1"},
    }
    run(tmp_path, max_bytes=100, extra_opts=hostile)
    opts = fakes["download"][0][1]["extra_opts"]
    assert opts["max_filesize"] == 100
    assert opts["postprocessors"][0]["preferredcodec"] == "mp3"
    assert opts["http_headers"] == {"X": "1"}  # deployment options still pass
    assert fakes["preview"][0][1]["extra_opts"]["http_headers"] == {"X": "1"}
    assert hostile["max_filesize"] == 10**12  # caller's dict untouched


@pytest.mark.parametrize("kw", [{"max_bytes": 0}, {"max_duration_s": -1}])
def test_caps_must_be_positive(fakes, tmp_path, kw):
    with pytest.raises(ValueError):
        run(tmp_path, **kw)

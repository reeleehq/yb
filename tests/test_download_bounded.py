"""``download_audio_bounded``: the policy, with yt-dlp calls faked (no network)."""

import pytest

pytest.importorskip("yt_dlp")  # the pinned match_filter is built by yt-dlp

from yb.download import (  # noqa: E402
    AudioLimitError,
    COPYRIGHT_NOTICE,
    download_audio_bounded,
    require_http_url,
)
from yb.download import bounded  # noqa: E402
from yb.download.youtube import DownloadResult  # noqa: E402


@pytest.fixture
def fakes(monkeypatch, tmp_path):
    """Fake the metadata fetch and the download; record what they were given."""
    seen = {
        "preview": [],
        "download": [],
        "size": 10,
        "write": True,
        "preview_info": {"duration": 60},
    }

    def extract(url, base_opts, **kw):
        seen["preview"].append((url, base_opts, kw))
        return seen["preview_info"]

    def download(url, *, download_dir, **kw):
        seen["download"].append((url, {"download_dir": download_dir, **kw}))
        if seen["write"]:
            (download_dir / "Song (id).mp3").write_bytes(b"x" * seen["size"])
        return DownloadResult(
            path=download_dir / "Song (id).webm",
            info={"id": "id", "title": "Song", "duration": 60},
        )

    monkeypatch.setattr(bounded, "_extract_info", extract)
    monkeypatch.setattr(bounded, "download_youtube_video", download)
    return seen


def run(tmp_path, **kw):
    return download_audio_bounded("https://example.com/v", download_dir=tmp_path, **kw)


def leftovers(tmp_path):
    return sorted(p.name for p in tmp_path.iterdir())


def test_happy_path_moves_mp3_into_download_dir(fakes, tmp_path):
    got = run(tmp_path, max_bytes=100, max_duration_s=120)
    assert got.path == tmp_path / "Song (id).mp3" and got.path.exists()
    assert (got.title, got.duration_s, got.notice) == ("Song", 60, COPYRIGHT_NOTICE)
    assert leftovers(tmp_path) == ["Song (id).mp3"]  # temp work dir is gone


def test_validator_runs_before_any_network(fakes, tmp_path):
    def refuse(url):
        raise ValueError("no")

    with pytest.raises(ValueError, match="no"):
        run(tmp_path, validate_target=refuse)
    assert not fakes["preview"] and not fakes["download"]


def test_resolved_page_url_is_validated_too(fakes, tmp_path):
    fakes["preview_info"] = {"duration": 5, "webpage_url": "http://169.254.169.254/x"}
    seen = []

    def validate(url):
        seen.append(url)
        if "169" in url:
            raise ValueError("private")

    with pytest.raises(ValueError, match="private"):
        run(tmp_path, validate_target=validate)
    assert seen == ["https://example.com/v", "http://169.254.169.254/x"]
    assert not fakes["download"]


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
    assert not fakes["download"]


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


def test_download_failure_cleans_the_work_dir(fakes, tmp_path, monkeypatch):
    def boom(url, **kw):
        kw["download_dir"].joinpath("x.part").write_bytes(b"1")
        raise RuntimeError("net")

    monkeypatch.setattr(bounded, "download_youtube_video", boom)
    with pytest.raises(RuntimeError):
        run(tmp_path)
    assert leftovers(tmp_path) == []


def test_pinned_opts_are_single_bounded_nonlive_mp3(fakes, tmp_path):
    run(tmp_path, max_bytes=100, extra_opts={"http_headers": {"X": "1"}})
    opts = fakes["download"][0][1]["extra_opts"]
    assert opts["max_filesize"] == 100
    assert opts["noplaylist"] and opts["max_downloads"] == 1
    assert opts["playlist_items"] == "1" and opts["keepvideo"] is False
    assert opts["postprocessors"][0]["preferredcodec"] == "mp3"
    assert opts["http_headers"] == {"X": "1"}  # deployment options pass through
    assert callable(opts["match_filter"])


def test_match_filter_rejects_long_and_live_but_not_unknown_duration(fakes, tmp_path):
    run(tmp_path, max_duration_s=100)
    flt = fakes["download"][0][1]["extra_opts"]["match_filter"]
    ok = {"id": "a", "title": "t", "duration": 99}
    assert flt(ok, incomplete=False) is None
    assert flt({**ok, "duration": 101}, incomplete=False) is not None
    assert flt({**ok, "is_live": True}, incomplete=False) is not None
    assert flt({"id": "a", "title": "t"}, incomplete=False) is None


@pytest.mark.parametrize(
    "key", ["max_filesize", "outtmpl", "noplaylist", "format", "match_filter", "paths"]
)
def test_extra_opts_outside_the_allowlist_raise(fakes, tmp_path, key):
    with pytest.raises(ValueError, match=key):
        run(tmp_path, extra_opts={key: 1})
    assert not fakes["preview"] and not fakes["download"]


@pytest.mark.parametrize("kw", [{"max_bytes": 0}, {"max_duration_s": -1}])
def test_caps_must_be_positive(fakes, tmp_path, kw):
    with pytest.raises(ValueError):
        run(tmp_path, **kw)

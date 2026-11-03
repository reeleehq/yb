"""Subtitles best-effort: a failed caption fetch does not sink the video (yt-dlp faked)."""

import sys
import types
from pathlib import Path

import pytest

from yb.download import (
    RateLimitedError,
    download_youtube_audio,
    download_youtube_subtitles,
    download_youtube_video,
)
from yb.download import requirements as req

SUBS_429 = "ERROR: Unable to download video subtitles for 'en': HTTP Error 429: Too Many Requests"


class _FakeYDL:
    seen: list = []
    errors: list = []  # raised by successive extract_info calls, None = succeed

    def __init__(self, opts):
        self.opts = opts
        type(self).seen.append(opts)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        error = type(self).errors.pop(0) if type(self).errors else None
        if error:
            raise error
        info = {"id": "abc", "title": "T"}
        if self.opts.get("skip_download"):
            # yt-dlp writes subtitles beside the name the video would have
            Path(self.prepare_filename(info)).with_suffix(".en.vtt").write_text("x")
        return info

    def prepare_filename(self, info):
        return str(Path(self.opts["outtmpl"]).parent / "T (abc).mp4")


@pytest.fixture
def ydl(monkeypatch, tmp_path):
    monkeypatch.setitem(
        sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=_FakeYDL)
    )
    monkeypatch.setattr(req, "check_requirements", lambda **k: [])
    monkeypatch.setattr(req, "find_js_runtime", lambda: None)
    req._preflight_opts.cache_clear()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.delenv("YB_COOKIES_FILE", raising=False)
    _FakeYDL.seen, _FakeYDL.errors = [], []
    yield _FakeYDL
    req._preflight_opts.cache_clear()


def get(tmp_path, **kw):
    return download_youtube_video(
        "u",
        download_dir=tmp_path,
        write_subtitles=True,
        write_auto_subtitles=True,
        **kw,
    )


def test_a_429_on_the_captions_retries_once_without_subtitles(ydl, tmp_path):
    ydl.errors = [Exception(SUBS_429)]
    with pytest.warns(UserWarning, match="without subtitles") as w:
        r = get(tmp_path)
    assert w[0].filename == __file__
    assert len(ydl.seen) == 2
    assert ydl.seen[0]["writesubtitles"] and ydl.seen[0]["writeautomaticsub"]
    assert not ydl.seen[1]["writesubtitles"] and not ydl.seen[1]["writeautomaticsub"]
    assert r.subtitles_error.startswith("Unable to download video subtitles for 'en'")
    assert "429" in r.subtitles_error and "Back off" not in r.subtitles_error
    assert r.video_id == "abc"


def test_the_retry_turns_subtitles_off_in_extra_opts_too(ydl, tmp_path):
    ydl.errors = [Exception(SUBS_429)]
    with pytest.warns(UserWarning):
        r = get(tmp_path, extra_opts={"writesubtitles": True, "proxy": "p"})
    assert ydl.seen[1]["writesubtitles"] is False and ydl.seen[1]["proxy"] == "p"
    assert r.subtitles_error


def test_another_download_error_passes_through_untouched(ydl, tmp_path):
    error = Exception("ERROR: [youtube] abc: Video unavailable")
    ydl.errors = [error]
    with pytest.raises(Exception) as got:
        get(tmp_path)
    assert got.value is error and len(ydl.seen) == 1


def test_any_subtitle_failure_is_skipped_not_only_a_rate_limit(ydl, tmp_path):
    ydl.errors = [
        Exception("ERROR: Unable to download video subtitles for 'en': HTTP Error 403")
    ]
    with pytest.warns(UserWarning):
        assert "403" in get(tmp_path).subtitles_error


def test_required_subtitles_raise_saying_only_the_subtitles_were_refused(ydl, tmp_path):
    ydl.errors = [Exception(SUBS_429)]
    with pytest.raises(RateLimitedError, match="Only the subtitles were refused"):
        get(tmp_path, on_subtitle_error="raise")
    assert len(ydl.seen) == 1


def test_required_subtitles_reraise_other_subtitle_errors_as_is(ydl, tmp_path):
    error = Exception(
        "ERROR: Unable to download video subtitles for 'en': HTTP Error 403"
    )
    ydl.errors = [error]
    with pytest.raises(Exception) as got:
        get(tmp_path, on_subtitle_error="raise")
    assert got.value is error


def test_a_video_failure_is_not_retried(ydl, tmp_path):
    ydl.errors = [Exception("ERROR: HTTP Error 429: Too Many Requests")]
    with pytest.raises(RateLimitedError):
        get(tmp_path)
    assert len(ydl.seen) == 1


def test_a_second_failure_propagates(ydl, tmp_path):
    ydl.errors = [Exception(SUBS_429), Exception("ERROR: HTTP Error 429")]
    with pytest.warns(UserWarning), pytest.raises(RateLimitedError):
        get(tmp_path)


def test_success_has_no_subtitles_error(ydl, tmp_path):
    assert get(tmp_path).subtitles_error is None


def test_unknown_policy_raises_before_any_fetch(ydl, tmp_path):
    with pytest.raises(ValueError, match="on_subtitle_error"):
        get(tmp_path, on_subtitle_error="best-effort")
    assert ydl.seen == []


def test_audio_passes_the_policy_through(ydl, tmp_path):
    ydl.errors = [Exception(SUBS_429)]
    with pytest.raises(RateLimitedError):
        download_youtube_audio(
            "u", download_dir=tmp_path, write_subtitles=True, on_subtitle_error="raise"
        )


def test_download_subtitles_fetches_only_subtitles(ydl, tmp_path):
    got = download_youtube_subtitles(
        "u", download_dir=tmp_path, subtitle_langs=("en", "fr"), pace="polite"
    )
    opts = ydl.seen[0]
    assert (
        opts["skip_download"] and opts["writesubtitles"] and opts["writeautomaticsub"]
    )
    assert opts["subtitleslangs"] == ["en", "fr"]
    assert opts["outtmpl"].startswith(str(tmp_path))
    assert opts["sleep_interval"] == 20 and opts["quiet"] is True
    assert got == [tmp_path / "T (abc).en.vtt"]


def test_download_subtitles_can_skip_auto(ydl, tmp_path):
    download_youtube_subtitles("u", download_dir=tmp_path, auto_subtitles=False)
    assert ydl.seen[0]["writeautomaticsub"] is False

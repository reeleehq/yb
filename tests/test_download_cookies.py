"""Cookies file for downloads: ``cookies_file`` / ``$YB_COOKIES_FILE`` / the default path.

Offline: yt-dlp is replaced by a recorder and the cookies files are fakes made in
``tmp_path`` (never a real cookie). HOME/USERPROFILE are pointed at ``tmp_path`` so the
developer's own ``~/.config/yb`` cannot leak into a test.
"""

import sys
from pathlib import Path
import types

import pytest

from yb.download import (
    download_youtube_audio,
    download_youtube_playlist,
    download_youtube_video,
    youtube_playlist_info,
    youtube_video_info,
)
from yb.download import requirements as req
from yb.download import youtube as ytdl


class _FakeYDL:
    seen: list = []

    def __init__(self, opts):
        type(self).seen.append(opts)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        if "list" in url:
            return {"id": "pl", "entries": []}
        return {"id": "abc", "title": "T"}

    def prepare_filename(self, info):
        return "/dl/T (abc).mp4"


@pytest.fixture
def ydl(monkeypatch, tmp_path):
    monkeypatch.setitem(
        sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=_FakeYDL)
    )
    monkeypatch.setattr(req, "check_requirements", lambda **k: [])
    monkeypatch.setattr(req, "find_js_runtime", lambda: None)
    req._preflight_opts.cache_clear()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))  # Windows expanduser
    monkeypatch.delenv(ytdl.COOKIES_FILE_ENV, raising=False)
    _FakeYDL.seen = []
    yield _FakeYDL
    req._preflight_opts.cache_clear()


def _fake_cookies(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Netscape HTTP Cookie File\n.example.test\tTRUE\t/\tTRUE\t0\tSID\tfake\n"
    )
    return path


def _default_file(tmp_path):
    return _fake_cookies(tmp_path / "home" / ".config" / "yb" / "youtube-cookies.txt")


def _calls(tmp_path):
    out = tmp_path / "out"
    return {
        "video_info": lambda **k: youtube_video_info("u", **k),
        "video": lambda **k: download_youtube_video("u", download_dir=out, **k),
        "audio": lambda **k: download_youtube_audio("u", download_dir=out, **k),
        "playlist_info": lambda **k: youtube_playlist_info("list", **k),
        "playlist": lambda **k: download_youtube_playlist(
            "list", download_dir=out, **k
        ),
    }


CALLS = ["video_info", "video", "audio", "playlist_info", "playlist"]


@pytest.mark.parametrize("name", CALLS)
def test_nothing_configured_changes_nothing(ydl, tmp_path, name):
    _calls(tmp_path)[name]()
    opts = ydl.seen[-1]
    assert "cookiefile" not in opts and "cookiesfrombrowser" not in opts


@pytest.mark.parametrize("name", CALLS)
def test_default_file_is_used_when_present(ydl, tmp_path, name):
    f = _default_file(tmp_path)
    _calls(tmp_path)[name]()
    assert ydl.seen[-1]["cookiefile"] == str(f)


def test_env_var_beats_the_default_file(ydl, tmp_path, monkeypatch):
    _default_file(tmp_path)
    mine = _fake_cookies(tmp_path / "elsewhere.txt")
    monkeypatch.setenv(ytdl.COOKIES_FILE_ENV, str(mine))
    download_youtube_video("u", download_dir=tmp_path)
    assert ydl.seen[-1]["cookiefile"] == str(mine)


def test_env_var_naming_a_missing_file_warns_and_sends_no_cookies(
    ydl, tmp_path, monkeypatch
):
    _default_file(tmp_path)
    monkeypatch.setenv(ytdl.COOKIES_FILE_ENV, str(tmp_path / "typo.txt"))
    with pytest.warns(UserWarning, match=ytdl.COOKIES_FILE_ENV):
        download_youtube_video("u", download_dir=tmp_path)
    assert "cookiefile" not in ydl.seen[-1]


@pytest.mark.parametrize("name", CALLS)
def test_explicit_cookies_file_wins_over_env_and_default(
    ydl, tmp_path, monkeypatch, name
):
    _default_file(tmp_path)
    monkeypatch.setenv(ytdl.COOKIES_FILE_ENV, str(_fake_cookies(tmp_path / "env.txt")))
    mine = _fake_cookies(tmp_path / "mine.txt")
    _calls(tmp_path)[name](cookies_file=mine)
    assert ydl.seen[-1]["cookiefile"] == str(mine)


def test_explicit_missing_cookies_file_fails_fast(ydl, tmp_path):
    with pytest.raises(FileNotFoundError, match="cookies_file"):
        download_youtube_video("u", download_dir=tmp_path, cookies_file=tmp_path / "no")
    assert ydl.seen == []


def test_false_opts_out_of_the_default(ydl, tmp_path):
    _default_file(tmp_path)
    download_youtube_video("u", download_dir=tmp_path, cookies_file=False)
    assert "cookiefile" not in ydl.seen[-1]


def test_explicit_cookies_from_browser_suppresses_the_default(ydl, tmp_path):
    _default_file(tmp_path)
    download_youtube_playlist(
        "list", download_dir=tmp_path, cookies_from_browser="safari"
    )
    opts = ydl.seen[-1]
    assert opts["cookiesfrombrowser"] == ("safari",)
    assert "cookiefile" not in opts


@pytest.mark.parametrize(
    "extra",
    [{"cookiefile": "/mine.txt"}, {"cookiesfrombrowser": ("chrome",)}],
)
@pytest.mark.parametrize("name", CALLS)
def test_extra_opts_cookies_win_over_the_default(ydl, tmp_path, name, extra):
    _default_file(tmp_path)
    _calls(tmp_path)[name](extra_opts=extra)
    opts = ydl.seen[-1]
    assert {k: opts[k] for k in extra} == extra
    assert opts.get("cookiefile") == extra.get("cookiefile")


def test_extra_opts_cookiefile_wins_over_explicit_cookies_file(ydl, tmp_path):
    mine = _fake_cookies(tmp_path / "mine.txt")
    download_youtube_video(
        "u",
        download_dir=tmp_path,
        cookies_file=mine,
        extra_opts={"cookiefile": "/theirs.txt"},
    )
    assert ydl.seen[-1]["cookiefile"] == "/theirs.txt"


SECRET = "SECRETVALUE123"


def _bad_cookies(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    # space-separated instead of tab-separated: yt-dlp would echo this line
    path.write_text(
        f"# Netscape HTTP Cookie File\n.youtube.com TRUE / TRUE 0 SID {SECRET}\n"
    )
    return path


def test_malformed_explicit_file_fails_without_leaking_values(ydl, tmp_path):
    bad = _bad_cookies(tmp_path / "bad.txt")
    with pytest.raises(ValueError, match=r"\[2\]") as e:
        download_youtube_video("u", download_dir=tmp_path, cookies_file=bad)
    assert SECRET not in str(e.value) and ydl.seen == []


def test_malformed_default_file_warns_without_leaking_values(ydl, tmp_path):
    _bad_cookies(tmp_path / "home" / ".config" / "yb" / "youtube-cookies.txt")
    with pytest.warns(UserWarning, match="Netscape") as w:
        download_youtube_video("u", download_dir=tmp_path)
    assert all(SECRET not in str(x.message) for x in w)
    assert "cookiefile" not in ydl.seen[-1]


def test_httponly_and_comment_lines_are_well_formed(ydl, tmp_path):
    f = tmp_path / "ok.txt"
    f.write_text(
        "# Netscape HTTP Cookie File\n\n"
        "#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tfake\n"
    )
    download_youtube_video("u", download_dir=tmp_path, cookies_file=f)
    assert ydl.seen[-1]["cookiefile"] == str(f)


def test_explicit_cookies_file_with_a_browser_source_is_refused(ydl, tmp_path):
    mine = _fake_cookies(tmp_path / "mine.txt")
    with pytest.raises(ValueError, match="browser"):
        download_youtube_playlist(
            "list",
            download_dir=tmp_path,
            cookies_file=mine,
            cookies_from_browser="safari",
        )
    with pytest.raises(ValueError, match="browser"):
        download_youtube_video(
            "u",
            download_dir=tmp_path,
            cookies_file=mine,
            extra_opts={"cookiesfrombrowser": ("chrome",)},
        )
    assert ydl.seen == []


def test_missing_env_file_warning_points_at_the_caller(ydl, tmp_path, monkeypatch):
    monkeypatch.setenv(ytdl.COOKIES_FILE_ENV, str(tmp_path / "typo.txt"))
    with pytest.warns(UserWarning) as w:
        download_youtube_video("u", download_dir=tmp_path)
    assert w[0].filename == __file__


# ---- private copy: unwritable file / parallel workers --------------------------


@pytest.fixture
def copy_probe(monkeypatch):
    """Record, at yt-dlp construction time, the cookiefile path, its mode and content."""
    probes = []
    original = _FakeYDL.__init__

    def init(self, opts):
        original(self, opts)
        path = opts.get("cookiefile")
        if path:
            import os
            import stat

            probes.append(
                (path, stat.S_IMODE(os.stat(path).st_mode), open(path).read())
            )

    monkeypatch.setattr(_FakeYDL, "__init__", init)
    return probes


@pytest.mark.parametrize("name", CALLS)
def test_unwritable_file_is_replaced_by_a_private_copy_then_deleted(
    ydl, tmp_path, monkeypatch, copy_probe, name
):
    f = _default_file(tmp_path)
    monkeypatch.setattr(ytdl.os, "access", lambda p, mode: False)
    _calls(tmp_path)[name]()
    ((copy, mode, content),) = copy_probe
    assert copy != str(f) and content == f.read_text()
    if hasattr(ytdl.os, "geteuid"):  # POSIX permission bits
        assert mode == 0o600
    assert not Path(copy).exists()
    assert f.read_text() == content  # the original is untouched


def test_copy_is_deleted_even_when_the_download_fails(
    ydl, tmp_path, monkeypatch, copy_probe
):
    _default_file(tmp_path)
    monkeypatch.setenv(ytdl.COOKIES_PRIVATE_COPY_ENV, "1")

    def boom(self, url, download=False):
        raise RuntimeError("net")

    monkeypatch.setattr(_FakeYDL, "extract_info", boom)
    with pytest.raises(RuntimeError):
        youtube_video_info("u")
    assert not Path(copy_probe[0][0]).exists()


def test_env_asks_for_a_copy_of_a_writable_file(ydl, tmp_path, monkeypatch, copy_probe):
    f = _default_file(tmp_path)
    youtube_video_info("u")
    assert ydl.seen[-1]["cookiefile"] == str(f)  # writable: as is
    monkeypatch.setenv(ytdl.COOKIES_PRIVATE_COPY_ENV, "true")
    youtube_video_info("u")
    assert ydl.seen[-1]["cookiefile"] != str(f)


def test_no_cookies_means_no_copy(ydl, tmp_path, monkeypatch, copy_probe):
    monkeypatch.setenv(ytdl.COOKIES_PRIVATE_COPY_ENV, "1")
    youtube_video_info("u")
    assert "cookiefile" not in ydl.seen[-1] and not copy_probe

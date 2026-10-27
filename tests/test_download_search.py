"""``search_youtube``: yt-dlp is faked, so no network is touched."""

import sys
import types

import pytest

from yb.download import SearchHit, search_youtube
from yb.download import youtube as ytdl


@pytest.fixture
def fake_ydl(monkeypatch):
    """Replace ``yt_dlp.YoutubeDL``; the fake records opts and the query."""
    calls = {}

    class FakeYDL:
        def __init__(self, opts):
            calls["opts"] = opts

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, query, download):
            calls["query"], calls["download"] = query, download
            return calls["result"]

    module = types.ModuleType("yt_dlp")
    module.YoutubeDL = FakeYDL
    monkeypatch.setitem(sys.modules, "yt_dlp", module)
    monkeypatch.setattr(ytdl, "with_runtime_opts", lambda o: o)
    monkeypatch.setattr(ytdl, "default_cookies_file", lambda: None)
    return calls


def test_returns_rows_and_builds_ytsearch_query(fake_ydl):
    fake_ydl["result"] = {
        "entries": [
            {
                "id": "a1",
                "title": "Song",
                "duration": 61,
                "channel": "Ch",
                "url": "https://www.youtube.com/watch?v=a1",
            },
            None,
            {"id": "b2", "title": "Live", "duration": None, "uploader": "Up"},
        ]
    }
    hits = search_youtube("हनुमान चालीसा", limit=2)
    assert fake_ydl["query"] == "ytsearch2:हनुमान चालीसा"
    assert fake_ydl["download"] is False
    assert fake_ydl["opts"]["extract_flat"] is True
    assert hits == [
        SearchHit("a1", "Song", 61, "Ch", "https://www.youtube.com/watch?v=a1"),
        SearchHit("b2", "Live", None, "Up", "https://www.youtube.com/watch?v=b2"),
    ]


def test_no_results_is_empty_list(fake_ydl):
    fake_ydl["result"] = None
    assert search_youtube("zzz") == []


def test_extra_opts_win_and_cookies_are_used(fake_ydl, tmp_path):
    cookies = tmp_path / "c.txt"
    cookies.write_text("# Netscape\n.youtube.com\tTRUE\t/\tTRUE\t0\tk\tv\n")
    fake_ydl["result"] = {"entries": []}
    search_youtube("x", cookies_file=cookies, extra_opts={"quiet": False})
    assert fake_ydl["opts"]["cookiefile"] == str(cookies)
    assert fake_ydl["opts"]["quiet"] is False


@pytest.mark.parametrize("query,limit", [("", 3), ("  ", 3), ("x", 0), ("x", 51)])
def test_bad_arguments_fail_before_any_request(fake_ydl, query, limit):
    with pytest.raises(ValueError):
        search_youtube(query, limit=limit)
    assert "query" not in fake_ydl

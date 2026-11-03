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
    monkeypatch.setattr(ytdl, "with_runtime_opts", lambda o: {**o, "_rt": True})
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
            {"title": "no id, no url"},
            {"id": "b2", "title": "Live", "duration": None, "uploader": "Up"},
        ]
    }
    hits = search_youtube("हनुमान चालीसा", limit=2)
    assert fake_ydl["query"] == "ytsearch2:हनुमान चालीसा"
    assert fake_ydl["download"] is False
    assert fake_ydl["opts"]["extract_flat"] is True
    assert fake_ydl["opts"]["_rt"] is True  # went through the JS-runtime step
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


def test_playlist_flat_rows_share_the_url_rule_but_never_invent_one(fake_ydl):
    fake_ydl["result"] = {
        "id": "pl",
        "entries": [
            {"id": "a1", "title": "A", "duration": 5, "url": "https://x/a1"},
            {"id": "b2", "title": "B", "webpage_url": "https://x/b2"},
            {"id": "c3"},
            {},
            None,
        ],
    }
    rows = ytdl.youtube_playlist_info("https://y/list")["entries"]
    assert rows == [
        {"id": "a1", "title": "A", "webpage_url": "https://x/a1", "duration": 5},
        {"id": "b2", "title": "B", "webpage_url": "https://x/b2", "duration": None},
        # no URL of its own: stays None (no made-up YouTube link)
        {"id": "c3", "title": None, "webpage_url": None, "duration": None},
    ]  # `{}` and `None` entries are skipped


def _hits(*durations):
    return {
        "entries": [
            {"id": f"v{i}", "title": f"T{i}", "duration": d, "view_count": i * 10}
            for i, d in enumerate(durations)
        ]
    }


def test_creative_commons_searches_the_filtered_results_page(fake_ydl):
    from urllib.parse import parse_qs, urlparse

    fake_ydl["result"] = _hits(60)
    search_youtube("house dance & footwork", limit=20, creative_commons=True)
    url = urlparse(fake_ydl["query"])
    assert f"{url.scheme}://{url.netloc}{url.path}" == ytdl.SEARCH_RESULTS_URL
    # YouTube's own links carry the filter double-encoded: sp=EgIwAQ%253D%253D
    assert "sp=EgIwAQ%253D%253D" in url.query
    assert parse_qs(url.query) == {
        "search_query": ["house dance & footwork"],
        "sp": [ytdl.CREATIVE_COMMONS_SP],
    }
    assert fake_ydl["opts"]["playlistend"] == 20
    assert fake_ydl["opts"]["extract_flat"] is True


def test_results_page_never_returns_more_than_limit(fake_ydl):
    fake_ydl["result"] = _hits(*[60] * 30)
    assert len(search_youtube("x", limit=3, creative_commons=True)) == 3


def test_duration_bounds_are_inclusive_and_drop_unknown(fake_ydl):
    fake_ydl["result"] = _hits(44, 45, 900, 901, None)
    hits = search_youtube("x", limit=5, min_s=45, max_s=900)
    assert [h.duration for h in hits] == [45, 900]
    assert fake_ydl["query"] == "ytsearch5:x"  # no YouTube filter: plain search


def test_one_bound_alone(fake_ydl):
    fake_ydl["result"] = _hits(10, 100, None)
    assert [h.duration for h in search_youtube("x", min_s=50)] == [100]
    assert [h.duration for h in search_youtube("x", max_s=50)] == [10]


def test_no_bound_keeps_unknown_durations(fake_ydl):
    fake_ydl["result"] = _hits(None)
    assert [h.duration for h in search_youtube("x")] == [None]


def test_view_count_is_carried(fake_ydl):
    fake_ydl["result"] = _hits(5, 6)
    assert [h.view_count for h in search_youtube("x")] == [0, 10]


def test_inverted_bounds_fail_before_any_request(fake_ydl):
    with pytest.raises(ValueError, match="min_s"):
        search_youtube("x", min_s=10, max_s=5)
    assert "query" not in fake_ydl

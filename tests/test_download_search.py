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

        def extract_info(self, query, download, process=True):
            calls["query"], calls["download"], calls["process"] = query, download, process
            calls["read"] = 0
            if calls["result"] is None:
                return None
            result = dict(calls["result"])

            def rows(entries):  # lazy, as yt-dlp's unprocessed entries are; counts reads
                for e in entries:
                    calls["read"] += 1
                    yield e

            result["entries"] = rows(result.get("entries") or [])
            return result

    module = types.ModuleType("yt_dlp")
    module.YoutubeDL = FakeYDL
    monkeypatch.setitem(sys.modules, "yt_dlp", module)
    monkeypatch.setattr(ytdl, "with_runtime_opts", lambda o: {**o, "_rt": True})
    monkeypatch.setattr(ytdl, "default_cookies_file", lambda: None)
    return calls


def _page(query):
    """``(base url, query string dict)`` of a results-page search."""
    from urllib.parse import parse_qs, urlparse

    url = urlparse(query)
    return f"{url.scheme}://{url.netloc}{url.path}", parse_qs(url.query)


def test_returns_rows_and_searches_the_videos_only_results_page(fake_ydl):
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
    # the search ytsearch2: makes: the results page, videos only, two rows
    assert _page(fake_ydl["query"]) == (
        ytdl.SEARCH_RESULTS_URL,
        {"search_query": ["हनुमान चालीसा"], "sp": [ytdl.VIDEOS_SP]},
    )
    assert fake_ydl["process"] is False  # lazy entries: pages fetched as rows are read
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
    search_youtube("C# & F+ é 日本 #tag", limit=20, creative_commons=True)
    url = urlparse(fake_ydl["query"])
    assert f"{url.scheme}://{url.netloc}{url.path}" == ytdl.SEARCH_RESULTS_URL
    assert parse_qs(url.query) == {
        "search_query": ["C# & F+ é 日本 #tag"],
        "sp": [ytdl.CREATIVE_COMMONS_SP],
    }
    assert fake_ydl["opts"]["extract_flat"] is True


def test_results_page_never_returns_more_than_limit(fake_ydl):
    fake_ydl["result"] = _hits(*[60] * 30)
    assert len(search_youtube("x", limit=3, creative_commons=True)) == 3


def test_duration_bounds_are_inclusive_and_drop_unknown(fake_ydl):
    fake_ydl["result"] = _hits(44, 45, 900, 901, None)
    hits = search_youtube("x", limit=5, min_s=45, max_s=900)
    assert [h.duration for h in hits] == [45, 900]
    assert _page(fake_ydl["query"])[1]["sp"] == [ytdl.VIDEOS_SP]


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


def test_channel_and_playlist_rows_are_not_hits(fake_ydl):
    fake_ydl["result"] = {
        "entries": [
            {
                "ie_key": "YoutubeTab",
                "id": "UC8butISFwT",
                "url": "https://y/channel/UC8",
            },
            {"ie_key": "YoutubeTab", "id": "PLx", "url": "https://y/playlist?list=PLx"},
            {"ie_key": "Youtube", "id": "v1", "title": "T", "duration": 60},
        ]
    }
    assert [h.id for h in search_youtube("x", creative_commons=True)] == ["v1"]


@pytest.mark.parametrize("bound", [float("nan"), float("inf"), -1, "45", True])
def test_bad_bounds_fail_before_any_request(fake_ydl, bound):
    with pytest.raises(ValueError, match="non-negative number"):
        search_youtube("x", min_s=bound)
    with pytest.raises(ValueError, match="non-negative number"):
        search_youtube("x", max_s=bound)
    assert "query" not in fake_ydl


def test_upload_date_is_iso_or_none(fake_ydl):
    """#78: from ``upload_date`` or a timestamp; ``None`` when the flat entry has neither."""
    fake_ydl["result"] = {
        "entries": [
            {"id": "a", "title": "A", "upload_date": "20261113"},
            {"id": "b", "title": "B", "timestamp": 1794000000},
            {"id": "c", "title": "C"},
        ]
    }
    assert [h.upload_date for h in search_youtube("x")] == [
        "2026-11-13",
        "2026-11-06",
        None,
    ]


def test_a_filter_reads_past_limit_until_limit_hits_pass(fake_ydl):
    fake_ydl["result"] = _hits(10, 20, 60, 30, 70, 80, 90)
    hits = search_youtube("x", limit=2, min_s=45)
    assert [h.duration for h in hits] == [60, 70]  # the first two that pass, in order
    assert fake_ydl["read"] == 5  # and no row (no page) more
    assert search_youtube("x", limit=2, min_s=45, scan=4) == hits[:1]
    assert fake_ydl["read"] == 4


def test_without_a_filter_only_limit_rows_are_read(fake_ydl):
    fake_ydl["result"] = _hits(*[60] * 30)
    assert len(search_youtube("x", limit=3)) == 3
    assert fake_ydl["read"] == 3


def test_keep_is_a_predicate_on_hits(fake_ydl):
    fake_ydl["result"] = _hits(60, 61, 62, 63)
    hits = search_youtube("x", limit=5, keep=lambda h: h.duration % 2 == 1)
    assert [h.duration for h in hits] == [61, 63]


def test_sp_is_youtubes_filter_and_creative_commons_its_shorthand(fake_ydl):
    fake_ydl["result"] = _hits(60)
    search_youtube("x", sp="EgIIAg==")  # e.g. uploaded this week
    assert _page(fake_ydl["query"])[1]["sp"] == ["EgIIAg=="]
    search_youtube("x", creative_commons=True)
    assert _page(fake_ydl["query"])[1]["sp"] == [ytdl.CREATIVE_COMMONS_SP]


def test_a_filter_menu_links_sp_is_decoded_and_empty_means_no_filter(fake_ydl):
    fake_ydl["result"] = _hits(60)
    search_youtube("x", sp="EgIIAg%253D%253D")  # as YouTube's own link carries it
    assert _page(fake_ydl["query"])[1]["sp"] == ["EgIIAg=="]
    search_youtube("x", sp="")
    assert "sp" not in _page(fake_ydl["query"])[1]


@pytest.mark.parametrize("kwargs", [dict(limit=2.5), dict(limit=True), dict(min_s=1, scan=10.0)])
def test_counts_must_be_ints(fake_ydl, kwargs):
    with pytest.raises(TypeError):
        search_youtube("x", **kwargs)
    assert "query" not in fake_ydl


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(sp="EgIIAg==", creative_commons=True),
        dict(limit=10, scan=5),
        dict(min_s=1, scan=ytdl.MAX_SEARCH_LIMIT + 1),
    ],
)
def test_conflicting_or_out_of_range_options_fail_before_any_request(fake_ydl, kwargs):
    with pytest.raises(ValueError):
        search_youtube("x", **kwargs)
    assert "query" not in fake_ydl

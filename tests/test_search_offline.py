"""``yb.youtube.search`` with the network call replaced: URL building, parsing, ranking, backend choice."""

import json

import pytest

from yb.youtube import search as S


def test_urls_and_thumbnail_quality():
    assert S.watch_url("abc") == "https://www.youtube.com/watch?v=abc"
    assert S.thumbnail_url("abc", quality="hqdefault").endswith("/abc/hqdefault.jpg")
    with pytest.raises(ValueError, match="quality must be one of"):
        S.thumbnail_url("abc", quality="huge")


def test_api_key_precedence(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    assert S._api_key() is None
    monkeypatch.setenv("YOUTUBE_API_KEY", "y")
    assert S._api_key() == "y"
    monkeypatch.setenv("GOOGLE_API_KEY", "g")
    assert S._api_key() == "g"
    assert S._api_key("explicit") == "explicit"


def test_api_available_needs_a_key_and_a_working_call(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    assert S.api_available() is False
    monkeypatch.setattr(S, "_get", lambda url, timeout=30: "{}")
    assert S.api_available(api_key="k") is True

    def boom(url, timeout=30):
        raise OSError("403")

    monkeypatch.setattr(S, "_get", boom)
    assert S.api_available(api_key="k") is False


def _api_page(ids, token=None):
    body = {
        "items": [
            {"id": {"videoId": i}, "snippet": {"title": f"T{i}", "channelTitle": "C", "publishedAt": "2020"}}
            for i in ids
        ]
    }
    if token:
        body["nextPageToken"] = token
    return json.dumps(body)


def test_api_search_pages_until_enough_and_passes_bias_params(monkeypatch):
    urls = []
    pages = iter([_api_page(["a", "b"], token="next"), _api_page(["c", "d"])])

    def fake(url, timeout=30):
        urls.append(url)
        return next(pages)

    monkeypatch.setattr(S, "_get", fake)
    out = S.search_videos("q", max_results=3, backend="api", api_key="k", language="en", region="GB")
    assert [v["video_id"] for v in out] == ["a", "b", "c"]
    assert all(v["source"] == "api" for v in out)
    assert "relevanceLanguage=en" in urls[0] and "regionCode=GB" in urls[0]
    assert "pageToken=next" in urls[1]


def test_api_search_without_a_key_refuses(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="no API key"):
        S.search_videos("q", backend="api")


def _scrape_html(*renderers):
    data = {"contents": [{"videoRenderer": r} for r in renderers] + [{"other": 1}]}
    return f"<script>var ytInitialData = {json.dumps(data)};</script>"


def test_scrape_search_dedupes_stops_at_max_and_parses_text_runs(monkeypatch):
    r = lambda i: {
        "videoId": i,
        "title": {"runs": [{"text": "Hello "}, {"text": i}]},
        "ownerText": {"runs": [{"text": "Chan"}]},
        "lengthText": {"simpleText": "3:21"},
    }
    html = _scrape_html(r("a"), r("a"), {"title": {}}, r("b"), r("c"))
    seen = []
    monkeypatch.setattr(S, "_get", lambda url, timeout=30: seen.append(url) or html)
    out = S.search_videos("q", max_results=2, backend="scrape", language="fr")
    assert [v["video_id"] for v in out] == ["a", "b"]
    assert out[0]["title"] == "Hello a" and out[0]["channel"] == "Chan" and out[0]["length"] == "3:21"
    assert out[0]["source"] == "scrape" and "hl=fr" in seen[0] and "gl=US" in seen[0]


def test_scrape_when_layout_changed_says_so(monkeypatch):
    monkeypatch.setattr(S, "_get", lambda url, timeout=30: "<html>nothing</html>")
    with pytest.raises(RuntimeError, match="page layout changed"):
        S.search_videos("q", backend="scrape")


def test_backend_validation_and_auto_fallback(monkeypatch):
    with pytest.raises(ValueError, match="auto/api/scrape"):
        S.search_videos("q", backend="bing")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.setattr(S, "_get", lambda url, timeout=30: _scrape_html({"videoId": "z", "title": {"simpleText": "Z"}}))
    out = S.search_videos("q")
    assert out[0]["source"] == "scrape"


def test_api_stats_batches_ids_by_fifty(monkeypatch):
    calls = []

    def fake(url, timeout=30):
        calls.append(url)
        return json.dumps(
            {"items": [{"id": "v0", "statistics": {"viewCount": "10", "likeCount": "2"}, "contentDetails": {"duration": "PT1M"}}]}
        )

    monkeypatch.setattr(S, "_get", fake)
    out = S._stats_api([f"v{i}" for i in range(120)], api_key="k")
    assert len(calls) == 3
    assert out["v0"] == {"views": 10, "likes": 2, "comments": None, "duration": "PT1M"}


def test_scrape_stats_reads_views_and_tolerates_failures(monkeypatch):
    pages = {
        "https://www.youtube.com/watch?v=a": '..."viewCount":{"simpleText":"1,234 views"}..."lengthSeconds":"61"',
        "https://www.youtube.com/watch?v=b": '"viewCount":"99"',
    }

    def fake(url, timeout=30):
        if url not in pages:
            raise OSError("gone")
        return pages[url]

    monkeypatch.setattr(S, "_get", fake)
    out = S._stats_scrape(["a", "b", "c"])
    assert out["a"]["views"] == 1234 and out["a"]["duration_seconds"] == 61 and out["a"]["likes"] is None
    assert out["b"]["views"] == 99
    assert out["c"] == {"views": None, "likes": None, "comments": None}


def test_add_stats_picks_backend_and_merges(monkeypatch):
    monkeypatch.setattr(S, "_stats_scrape", lambda ids: {"a": {"views": 5}})
    vids = [{"video_id": "a"}, {"video_id": "b"}]
    assert S.add_stats(vids, backend="scrape")[0]["views"] == 5
    assert S.add_stats([], backend="scrape") == []
    monkeypatch.setattr(S, "_stats_api", lambda ids, api_key=None: {"a": {"views": 9}})
    assert S.add_stats([{"video_id": "a"}], backend="api")[0]["views"] == 9
    monkeypatch.setattr(S, "api_available", lambda **kw: True)
    assert S.add_stats([{"video_id": "a"}])[0]["views"] == 9


def test_with_stats_flag_adds_numbers(monkeypatch):
    monkeypatch.setattr(S, "_search_scrape", lambda q, **kw: [{"video_id": "a"}])
    monkeypatch.setattr(S, "_stats_scrape", lambda ids: {"a": {"views": 7}})
    assert S.search_videos("q", backend="scrape", with_stats=True)[0]["views"] == 7


def test_rank_by_engagement_rewards_approval_and_sorts_missing_last():
    vids = [
        {"video_id": "big", "views": 1_000_000, "likes": 100},
        {"video_id": "loved", "views": 10_000, "likes": 2_000},
        {"video_id": "none", "views": None},
        {"video_id": "tiny", "views": 5, "likes": None},
    ]
    ranked = S.rank_by_engagement(vids)
    assert [v["video_id"] for v in ranked][0] == "loved"
    assert ranked[-1]["video_id"] == "none" and ranked[-1]["engagement_score"] == -1.0
    kept = S.rank_by_engagement([dict(v) for v in vids], min_views=100)
    assert "tiny" not in [v["video_id"] for v in kept] and "none" in [v["video_id"] for v in kept]

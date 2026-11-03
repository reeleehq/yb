"""Playlist items whose subtitles fail are not dropped (real yt-dlp, local server).

yt-dlp's generic extractor reads an HTML page with two ``<video>`` tags, each
with a ``<track>``, as a two-item playlist with subtitles, so a 429 on one
caption reproduces the YouTube case without the network or ffmpeg.
"""

import http.server
import threading

import pytest

pytest.importorskip("yt_dlp")

from yb.download import (  # noqa: E402
    PlaylistSubtitleError,
    SubtitleFailure,
    download_youtube_playlist,
)

PAGE = b"""<html><head><title>P</title></head><body>
<video src="/a.mp4"><track kind="subtitles" srclang="en" src="/a.vtt"></video>
<video src="/b.mp4"><track kind="subtitles" srclang="en" src="/b.vtt"></video>
</body></html>"""


class _Captions429(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    refused = "/a.vtt"
    page_hits = 0

    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/page.html":
            type(self).page_hits += 1
            self._send(200, PAGE, "text/html")
        elif self.path.endswith(".mp4"):
            self._send(200, b"\0" * 1000, "video/mp4")
        elif self.path == self.refused:
            self._send(429, b"slow down", "text/plain")
        elif self.path.endswith(".vtt"):
            self._send(200, b"WEBVTT\n\n00:00.000 --> 00:01.000\nhi\n", "text/vtt")
        else:
            self._send(404, b"", "text/plain")


@pytest.fixture
def page(monkeypatch):
    monkeypatch.setattr(_Captions429, "page_hits", 0)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Captions429)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/page.html"
    server.shutdown()


def get(page, tmp_path, *, extra_opts=None, **kw):
    return download_youtube_playlist(
        page,
        download_dir=tmp_path,
        fmt="best",
        merge_to=None,
        write_info_json=False,
        write_subtitles=True,
        cookies_file=False,
        extra_opts={"noprogress": True, **(extra_opts or {})},
        **kw,
    )


def test_an_item_whose_subtitles_fail_is_downloaded_again_without_them(page, tmp_path):
    with pytest.warns(UserWarning, match="without subtitles") as w:
        results = get(page, tmp_path)
    (ours,) = [x for x in w if "without subtitles" in str(x.message)]
    assert ours.filename == __file__  # not yt-dlp's frame
    assert [r.video_id for r in results] == ["page-1", "page-2"]  # playlist order
    first, second = results
    assert first.path.exists() and "HTTP Error 429" in first.subtitles_error
    assert not first.sidecars.get("subtitles")
    assert second.subtitles_error is None and second.sidecars["subtitles"]
    assert _Captions429.page_hits == 1  # retried in place, not re-extracted


@pytest.mark.parametrize(
    "kw,expected",
    [
        ({"skip_first": True}, [("page-2", True)]),
        ({"extra_opts": {"playlist_items": "2"}}, [("page-2", True)]),
        (
            {"filename_template": "%(playlist_autonumber)s.%(ext)s"},
            [("page-1", False), ("page-2", True)],
        ),
        ({"item_folders": True}, [("page-1", False), ("page-2", True)]),
    ],
)
def test_the_retry_keeps_the_selection_and_the_names(
    page, tmp_path, monkeypatch, kw, expected
):
    monkeypatch.setattr(_Captions429, "refused", "/b.vtt")
    with pytest.warns(UserWarning, match="without subtitles"):
        results = get(page, tmp_path, **kw)
    assert [(r.video_id, bool(r.subtitles_error)) for r in results] == expected
    assert len({r.path for r in results}) == len(results)
    assert all(r.path.exists() for r in results)


def test_order_is_kept_with_a_retry(page, tmp_path):
    with pytest.warns(UserWarning):
        results = get(
            page, tmp_path, extra_opts={"noprogress": True, "playlistreverse": True}
        )
    assert [r.video_id for r in results] == ["page-2", "page-1"]


def test_raise_reports_the_failed_items_and_keeps_the_rest(page, tmp_path):
    with pytest.raises(PlaylistSubtitleError, match="page-1") as got:
        get(page, tmp_path, on_subtitle_error="raise")
    assert [r.video_id for r in got.value.results] == ["page-2"]
    (failure,) = got.value.failures
    assert isinstance(failure, SubtitleFailure)
    assert failure.video_id == "page-1" and "HTTP Error 429" in failure.error
    assert not (tmp_path / "P (1) (page-1).mp4").exists()


def test_no_failure_no_subtitles_error(page, tmp_path, monkeypatch):
    monkeypatch.setattr(_Captions429, "refused", "/none")
    results = get(page, tmp_path)
    assert [r.subtitles_error for r in results] == [None, None]
    assert _Captions429.page_hits == 1


def test_unknown_policy_fails_before_any_request(tmp_path):
    with pytest.raises(ValueError, match="on_subtitle_error"):
        download_youtube_playlist("u", download_dir=tmp_path, on_subtitle_error="x")


def test_autonumber_is_not_skipped_by_a_retry(page, tmp_path):
    with pytest.warns(UserWarning):
        results = get(page, tmp_path, filename_template="%(autonumber)s.%(ext)s")
    assert sorted(r.path.name for r in results) == ["00001.mp4", "00002.mp4"]


def test_yt_dlp_still_has_the_hook_point():
    """The fallback wraps YoutubeDL.process_info; a rename must fail loudly here."""
    import yt_dlp

    assert callable(getattr(yt_dlp.YoutubeDL, "process_info", None))


def test_warnings_as_errors_do_not_drop_the_item(page, tmp_path):
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        from yb.download.requirements import DownloadRequirementWarning

        warnings.filterwarnings("ignore", category=DownloadRequirementWarning)
        results = get(page, tmp_path)
    assert [r.video_id for r in results] == ["page-1", "page-2"]

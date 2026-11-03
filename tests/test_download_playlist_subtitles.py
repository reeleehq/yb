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
def page():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Captions429)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/page.html"
    server.shutdown()


def get(page, tmp_path, **kw):
    return download_youtube_playlist(
        page,
        download_dir=tmp_path,
        fmt="best",
        merge_to=None,
        write_info_json=False,
        write_subtitles=True,
        cookies_file=False,
        extra_opts={"noprogress": True},
        **kw,
    )


def test_an_item_whose_subtitles_fail_is_downloaded_again_without_them(page, tmp_path):
    with pytest.warns(UserWarning, match="again without subtitles") as w:
        results = get(page, tmp_path)
    assert w[0].filename == __file__
    assert [r.video_id for r in results] == ["page-1", "page-2"]  # playlist order
    first, second = results
    assert first.path.exists() and "HTTP Error 429" in first.subtitles_error
    assert not first.sidecars.get("subtitles")
    assert second.subtitles_error is None and second.sidecars["subtitles"]


def test_raise_reports_the_failed_items_and_keeps_the_rest(page, tmp_path):
    with pytest.raises(PlaylistSubtitleError, match="page-1") as got:
        get(page, tmp_path, on_subtitle_error="raise")
    assert [r.video_id for r in got.value.results] == ["page-2"]
    (failure,) = got.value.failures
    assert isinstance(failure, SubtitleFailure)
    assert (failure.index, failure.video_id) == (1, "page-1")
    assert not (tmp_path / "P (1) (page-1).mp4").exists()


def test_no_failure_no_second_pass(page, tmp_path, monkeypatch):
    monkeypatch.setattr(_Captions429, "refused", "/none")
    results = get(page, tmp_path)
    assert [r.subtitles_error for r in results] == [None, None]


def test_unknown_policy_fails_before_any_request(tmp_path):
    with pytest.raises(ValueError, match="on_subtitle_error"):
        download_youtube_playlist("u", download_dir=tmp_path, on_subtitle_error="x")

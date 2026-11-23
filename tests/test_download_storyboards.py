"""yb.download.storyboards: a video's seek-bar frames by time, with a fake yt-dlp."""

import io

import pytest

import yb.download.youtube as ytdl
from yb.download.storyboards import Storyboard, StoryboardSheet, youtube_storyboard

PIL = pytest.importorskip("PIL.Image")


def _sheet(rows, cols, w, h, base):
    """A sprite sheet whose tile (r, c) is filled with grey level base + r*cols + c."""
    image = PIL.new("L", (cols * w, rows * h))
    for r in range(rows):
        for c in range(cols):
            image.paste(base + r * cols + c, (c * w, r * h, (c + 1) * w, (r + 1) * h))
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _fake(info, payloads):
    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    class FakeYDL:
        opened = []

        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download=False):
            assert download is False  # never a video download
            return info

        def urlopen(self, url):
            FakeYDL.opened.append(url)
            return Response(payloads[url])

    return FakeYDL


@pytest.fixture(autouse=True)
def _no_runtime(monkeypatch):
    monkeypatch.setattr(ytdl, "with_runtime_opts", lambda o: o)
    monkeypatch.setattr(ytdl, "default_cookies_file", lambda: None)


INFO = {
    "id": "vid1",
    "title": "A film",
    "duration": 7.5,
    "webpage_url": "https://www.youtube.com/watch?v=vid1",
    "license": "Creative Commons Attribution license (reuse allowed)",
    "uploader": "A Studio",
    "channel": "A Studio",
    "channel_url": "https://www.youtube.com/channel/UC123",
    "formats": [
        {"format_id": "18"},
        {
            "format_id": "sb0",
            "format_note": "storyboard",
            "width": 4,
            "height": 2,
            "rows": 2,
            "columns": 2,
            "fragments": [
                {"url": "https://i.ytimg.com/sb/M0.jpg", "duration": "4.0"},
                {"url": "https://i.ytimg.com/sb/M1.jpg", "duration": 4.0},
            ],
        },
    ],
}
PAYLOADS = {
    "https://i.ytimg.com/sb/M0.jpg": _sheet(2, 2, 4, 2, 10),
    "https://i.ytimg.com/sb/M1.jpg": _sheet(2, 2, 4, 2, 20),
}


def test_frames_are_cut_from_the_sheets_at_their_times():
    board = youtube_storyboard("u", ydl_cls=_fake(INFO, PAYLOADS))
    assert (board.video_id, board.title, board.duration) == ("vid1", "A film", 7.5)
    assert board.license.startswith("Creative Commons")
    assert (board.uploader, board.channel_url) == ("A Studio", "https://www.youtube.com/channel/UC123")
    frames = list(board.frames())
    # 8 tiles, but the video ends at 7.5 s: the tiles at 0..7 s are kept
    assert [t for t, _ in frames] == [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
    assert [im.getpixel((0, 0)) for _, im in frames] == [10, 11, 12, 13, 20, 21, 22, 23]
    assert all(im.size == (4, 2) for _, im in frames)


def test_a_video_without_that_storyboard_says_which_it_has():
    with pytest.raises(LookupError, match=r"no storyboard 'sb3' \(has: \['sb0'\]\)"):
        youtube_storyboard("u", format_id="sb3", ydl_cls=_fake(INFO, PAYLOADS))


def test_frame_times_stop_at_the_video_end():
    board = Storyboard(
        "v", "u", None, 5.0, None, "sb0", 4, 2, 1, 2,
        sheets=(StoryboardSheet(0.0, 4.0, b""), StoryboardSheet(4.0, 4.0, b"")),
    )
    assert board.frame_times() == [0.0, 2.0, 4.0]


def test_relative_fragment_paths_join_the_base_url():
    info = {
        **INFO,
        "formats": [
            {
                **INFO["formats"][1],
                "fragment_base_url": "https://i.ytimg.com/sb/",
                "fragments": [{"path": "M0.jpg", "duration": 8.0}],
            }
        ],
    }
    fake = _fake(info, PAYLOADS)
    youtube_storyboard("u", ydl_cls=fake)
    assert fake.opened == ["https://i.ytimg.com/sb/M0.jpg"]

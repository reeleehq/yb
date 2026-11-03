"""The synthetic-media disclosure reaches the upload body from every path (yb#63)."""

import pytest

from yb.config import YbConfig, load_config
from yb.content import PublicationContent
from yb.youtube import publish as P
from yb.youtube import VideoMetadata


@pytest.fixture
def bodies(monkeypatch, tmp_path):
    """Record each ``videos.insert`` body; no network, no playlist."""
    seen = []

    def upload_video(path, body, *, service, progress):
        seen.append(body)
        return {"id": "vid", "status": {"privacyStatus": "unlisted"}}

    monkeypatch.setattr(P, "upload_video", upload_video)
    media = tmp_path / "v.mp4"
    media.write_bytes(b"x")
    return seen, media


def _content(media):
    return PublicationContent(media=media, title="t", description="d")


def _flag(body):
    return body["status"].get("containsSyntheticMedia")


@pytest.mark.parametrize(
    "explicit,configured,expected",
    [
        (None, None, None),  # unset: the key is not sent at all
        (True, None, True),
        (False, True, False),  # the call wins over the config
        (None, True, True),  # the config supplies the default
    ],
)
def test_publish_content(bodies, explicit, configured, expected):
    seen, media = bodies
    P.publish_content(
        _content(media),
        contains_synthetic_media=explicit,
        config=YbConfig(contains_synthetic_media=configured),
        playlist=None,
        service=object(),
        progress=False,
    )
    assert _flag(seen[-1]) is expected
    assert ("containsSyntheticMedia" in seen[-1]["status"]) is (expected is not None)


def test_prepare_and_publish_forwards_it(bodies, monkeypatch):
    seen, media = bodies
    monkeypatch.setattr(P, "prepare_content", lambda m, **kw: _content(media))
    P.prepare_and_publish(
        media,
        contains_synthetic_media=True,
        config=YbConfig(),
        playlist=None,
        service=object(),
        progress=False,
    )
    assert _flag(seen[-1]) is True


@pytest.mark.parametrize(
    "on_metadata,configured,expected",
    [(None, True, True), (False, True, False), (True, None, True), (None, None, None)],
)
def test_publish_video_uses_the_config_when_the_metadata_leaves_it_unset(
    bodies, on_metadata, configured, expected
):
    seen, media = bodies
    meta = VideoMetadata(
        title="t", description="d", contains_synthetic_media=on_metadata
    )
    P.publish_video(
        media,
        meta,
        config=YbConfig(contains_synthetic_media=configured),
        playlist=None,
        service=object(),
        progress=False,
    )
    assert _flag(seen[-1]) is expected
    assert (
        meta.contains_synthetic_media is on_metadata
    )  # the caller's object is not changed


def test_the_config_file_key(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"profiles": {"ai": {"contains_synthetic_media": true}}}')
    assert load_config(path, profile="ai").contains_synthetic_media is True
    assert load_config(path).contains_synthetic_media is None


def test_a_call_privacy_wins_over_an_explicit_config(bodies):
    """Pre-existing leak: privacy_status was ignored when config= was passed."""
    seen, media = bodies
    for publish, first in [
        (P.publish_content, _content(media)),
        (P.publish_video, VideoMetadata(title="t", description="d")),
    ]:
        args = (first,) if publish is P.publish_content else (media, first)
        publish(
            *args,
            privacy_status="private",
            config=YbConfig(privacy_status="public"),
            playlist=None,
            service=object(),
            progress=False,
        )
        assert seen[-1]["status"]["privacyStatus"] == "private"


@pytest.mark.parametrize(
    "kw,error",
    [
        ({"contains_synthetic_media": "false"}, TypeError),
        ({"contains_synthetic_media": 1}, TypeError),
        ({"privacy_status": "Public"}, ValueError),
        ({"playlist_privacy_status": "secret"}, ValueError),
    ],
)
def test_config_values_are_checked(kw, error):
    with pytest.raises(error):
        YbConfig(**kw)


def test_metadata_cleanup_is_idempotent():
    from dataclasses import replace

    meta = VideoMetadata(title="a" * 99 + " b", description="d")
    assert replace(meta).title == meta.title == "a" * 99


def test_music_publish_forwards_the_flag(monkeypatch, tmp_path):
    music = pytest.importorskip("yb.music.publish")
    got = []
    monkeypatch.setattr(P, "publish_content", lambda c, **kw: got.append(kw) or {})
    video = type("MV", (), {"content": _content(tmp_path / "s.mp4")})()
    music.publish_music(
        [], prepared=[video], contains_synthetic_media=False, progress=False
    )
    assert got[0]["contains_synthetic_media"] is False

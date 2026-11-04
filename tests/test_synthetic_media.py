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


def _publish(kind, media, **kw):
    """Call ``publish_content`` or ``publish_video`` with minimal arguments."""
    if kind == "content":
        return P.publish_content(_content(media), **kw)
    return P.publish_video(media, VideoMetadata(title="t", description="d"), **kw)


@pytest.mark.parametrize("kind", ["content", "video"])
def test_a_call_privacy_wins_over_an_explicit_config(bodies, kind):
    """Pre-existing leak: privacy_status was ignored when config= was passed."""
    seen, media = bodies
    _publish(
        kind,
        media,
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


def test_null_in_the_config_file_means_the_default(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"privacy_status": null, "contains_synthetic_media": null}')
    cfg = load_config(path)
    assert (cfg.privacy_status, cfg.contains_synthetic_media) == ("unlisted", None)


@pytest.mark.parametrize("kind", ["content", "video"])
def test_an_invalid_privacy_fails_before_any_api_call(bodies, monkeypatch, kind):
    seen, media = bodies
    calls = []
    monkeypatch.setattr(P, "get_service", lambda *a, **k: calls.append("service"))
    with pytest.raises(ValueError, match="privacy_status"):
        _publish(
            kind, media, privacy_status="Public", config=YbConfig(), progress=False
        )
    assert calls == []

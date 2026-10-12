"""A failure after the upload keeps the video id and can be resumed (yb#21)."""

import pytest

from yb.config import YbConfig
from yb.youtube import publish as P
from yb.youtube import CaptionTrack, PartialPublish, VideoMetadata


class _Quota(Exception):
    pass


@pytest.fixture
def api(monkeypatch, tmp_path):
    """Record every API call; ``fail`` names steps that raise once."""
    calls: list[tuple] = []
    fail: set[str] = set()

    def upload_video(path, body, *, service, progress):
        calls.append(("upload", str(path)))
        return {"id": f"vid{sum(c[0] == 'upload' for c in calls)}", "status": {"privacyStatus": "unlisted"}}

    def step(name):
        def run(video_id, *a, **k):
            key = name if name != "caption" else f"caption {getattr(a[0], 'language', k.get('language'))}"
            calls.append((key, video_id))
            if key in fail:
                fail.discard(key)
                raise _Quota("quotaExceeded")
            return {"playlist_id": "PL1"} if name == "playlist" else None

        return run

    monkeypatch.setattr(P, "upload_video", upload_video)
    monkeypatch.setattr(P, "upsert_caption", step("caption"))
    monkeypatch.setattr(P, "set_thumbnail", step("thumbnail"))
    monkeypatch.setattr(P, "add_video_to_playlist", step("playlist"))
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    thumb = tmp_path / "t.png"
    thumb.write_bytes(b"x")
    caps = [CaptionTrack(tmp_path / "a.srt", "ja"), CaptionTrack(tmp_path / "b.srt", "en")]
    return calls, fail, video, thumb, caps


def _publish(video, thumb, caps, **kw):
    return P.publish_video(
        video,
        VideoMetadata(title="t", description="d"),
        captions=caps,
        thumbnail=thumb,
        playlist="Songs",
        config=YbConfig(),
        service=object(),
        progress=False,
        **kw,
    )


def test_a_failed_caption_raises_with_the_video_id_and_what_was_done(api):
    calls, fail, video, thumb, caps = api
    fail.add("caption en")

    with pytest.raises(PartialPublish) as err:
        _publish(video, thumb, caps)

    e = err.value
    assert e.result["video_id"] == "vid1"
    assert e.result["url"] == "https://youtu.be/vid1"
    assert e.result["captions"] == ["ja"]
    assert e.result["thumbnail"] is False and e.result["playlist"] is None
    assert e.step == "caption en"
    assert isinstance(e.__cause__, _Quota)
    assert "vid1" in str(e)


def test_resume_finishes_without_uploading_again(api):
    calls, fail, video, thumb, caps = api
    fail.add("caption en")
    with pytest.raises(PartialPublish) as err:
        _publish(video, thumb, caps)
    calls.clear()

    result = _publish(video, thumb, caps, resume=err.value.result)

    assert [c[0] for c in calls] == ["caption en", "thumbnail", "playlist"]
    assert all(c[1] == "vid1" for c in calls)
    assert result["captions"] == ["ja", "en"]
    assert result["thumbnail"] is True and result["playlist"] == {"playlist_id": "PL1"}


def test_resume_does_not_mutate_the_saved_result(api):
    calls, fail, video, thumb, caps = api
    fail.add("thumbnail")
    with pytest.raises(PartialPublish) as err:
        _publish(video, thumb, caps)
    saved = err.value.result
    snapshot = {**saved, "captions": list(saved["captions"])}

    _publish(video, thumb, caps, resume=saved)

    assert saved == snapshot


def test_a_failed_playlist_step_still_reports_the_id(api):
    calls, fail, video, thumb, caps = api
    fail.add("playlist")

    with pytest.raises(PartialPublish) as err:
        _publish(video, thumb, caps)

    assert err.value.step == "playlist"
    assert err.value.result["captions"] == ["ja", "en"]
    assert err.value.result["thumbnail"] is True


def test_success_returns_the_same_shape_as_before(api):
    calls, fail, video, thumb, caps = api

    result = _publish(video, thumb, caps)

    assert set(result) == {
        "video_id",
        "url",
        "studio_url",
        "privacy_status",
        "captions",
        "thumbnail",
        "playlist",
    }
    assert [c[0] for c in calls] == ["upload", "caption ja", "caption en", "thumbnail", "playlist"]


def test_a_failed_upload_is_not_a_partial_publish(api, monkeypatch):
    calls, fail, video, thumb, caps = api

    def boom(*a, **k):
        raise _Quota("quotaExceeded")

    monkeypatch.setattr(P, "upload_video", boom)
    with pytest.raises(_Quota):
        _publish(video, thumb, caps)


def test_resume_needs_a_video_id(api):
    calls, fail, video, thumb, caps = api
    with pytest.raises(ValueError, match="resume"):
        _publish(video, thumb, caps, resume={"captions": []})
    assert not calls

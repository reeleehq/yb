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
        return {
            "id": f"vid{sum(c[0] == 'upload' for c in calls)}",
            "status": {"privacyStatus": "unlisted"},
        }

    def step(name):
        def run(video_id, *a, **k):
            key = (
                name
                if name != "caption"
                else f"caption {getattr(a[0], 'language', k.get('language'))}"
            )
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
    caps = [
        CaptionTrack(tmp_path / "a.srt", "ja"),
        CaptionTrack(tmp_path / "b.srt", "en"),
    ]
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
    assert [c[0] for c in calls] == [
        "upload",
        "caption ja",
        "caption en",
        "thumbnail",
        "playlist",
    ]


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


def test_a_fresh_run_attaches_two_tracks_in_one_language(api, tmp_path):
    """Review of #22: steps are keyed on the language, and a fresh run must
    not skip the second one (before, both reached YouTube)."""
    calls, fail, video, thumb, _ = api
    caps = [
        CaptionTrack(tmp_path / "a.srt", "en", "A"),
        CaptionTrack(tmp_path / "b.srt", "en", "B"),
    ]

    _publish(video, thumb, caps)

    assert [c[0] for c in calls].count("caption en") == 2


def test_a_resume_runs_the_second_track_in_a_language_it_lacks(api, tmp_path):
    """yb#30: steps were marked done by language, so after the second of two
    "en" tracks failed, a resume skipped it."""
    calls, fail, video, thumb, _ = api
    caps = [
        CaptionTrack(tmp_path / "a.srt", "en", "A"),
        CaptionTrack(tmp_path / "b.srt", "en", "B"),
    ]

    result = _publish(
        video, thumb, caps, resume={"video_id": "vid1", "captions": ["en"]}
    )

    assert [c[0] for c in calls].count("caption en") == 1
    assert result["captions"] == ["en", "en"]


def test_a_hand_built_resume_gets_defaults_and_drops_extra_keys(api):
    calls, fail, video, thumb, caps = api

    result = _publish(video, thumb, caps, resume={"video_id": "vidX", "note": "mine"})

    assert "upload" not in [c[0] for c in calls]
    assert result["url"] == "https://youtu.be/vidX" and "note" not in result
    assert result["captions"] == ["ja", "en"] and result["thumbnail"] is True


def test_resume_survives_a_json_round_trip(api):
    import json

    calls, fail, video, thumb, caps = api
    fail.add("thumbnail")
    with pytest.raises(PartialPublish) as err:
        _publish(video, thumb, caps)
    saved = json.loads(json.dumps(err.value.result))
    calls.clear()

    _publish(video, thumb, caps, resume=saved)

    assert [c[0] for c in calls] == ["thumbnail", "playlist"]


def test_partial_publish_pickles(api):
    import pickle

    calls, fail, video, thumb, caps = api
    fail.add("playlist")
    with pytest.raises(PartialPublish) as err:
        _publish(video, thumb, caps)

    back = pickle.loads(pickle.dumps(err.value))

    assert back.result == err.value.result and back.step == "playlist"
    assert str(back) == str(err.value)


def test_publish_content_raises_and_resumes_the_same_way(api, tmp_path):
    from yb.content import PublicationContent

    calls, fail, video, thumb, _ = api
    srt = tmp_path / "a.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n")
    content = PublicationContent(
        media=video,
        title="t",
        description="d",
        language="ja",
        srt_path=srt,
        thumbnail=thumb,
    )
    kw = dict(playlist="Songs", config=YbConfig(), service=object(), progress=False)
    fail.add("thumbnail")

    with pytest.raises(PartialPublish) as err:
        P.publish_content(content, **kw)
    assert err.value.result["captions"] == ["ja"] and err.value.step == "thumbnail"
    calls.clear()

    result = P.publish_content(content, resume=err.value.result, **kw)

    assert [c[0] for c in calls] == ["thumbnail", "playlist"]
    assert result["thumbnail"] is True and result["video_id"] == "vid1"

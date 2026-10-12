"""Change a video's privacy, and retire an upload a re-cut replaces (yb#19)."""

import pytest

from yb.youtube import (
    playlists_containing,
    remove_from_playlist,
    supersede,
    update_video_status,
)


class _Req:
    def __init__(self, fn):
        self._fn = fn

    def execute(self):
        return self._fn()


class _Videos:
    def __init__(self, svc):
        self.svc = svc

    def list(self, *, part, id):
        st = self.svc.status.get(id)
        return _Req(lambda: {"items": [{"id": id, "status": dict(st)}] if st else []})

    def update(self, *, part, body):
        assert part == "status"

        def run():
            if self.svc.fail_update:
                raise RuntimeError("quotaExceeded")
            self.svc.status[body["id"]] = dict(body["status"])
            self.svc.updates.append(body)
            return body

        return _Req(run)


class _Playlists:
    def __init__(self, svc):
        self.svc = svc

    def list(self, **kw):
        return _Req(lambda: {"items": [{"id": p} for p in self.svc.items]})


class _Items:
    def __init__(self, svc):
        self.svc = svc

    def list(self, *, part, playlistId, maxResults, pageToken=None):
        rows = self.svc.items.get(playlistId, [])
        return _Req(
            lambda: {
                "items": [
                    {"id": f"{playlistId}:{i}", "contentDetails": {"videoId": v}}
                    for i, v in enumerate(rows)
                    if v is not None
                ]
            }
        )

    def insert(self, *, part, body):
        pid = body["snippet"]["playlistId"]

        def run():
            self.svc.items[pid].append(body["snippet"]["resourceId"]["videoId"])
            return {"id": "new"}

        return _Req(run)

    def delete(self, *, id):
        pid, i = id.rsplit(":", 1)

        def run():
            self.svc.items[pid][int(i)] = None  # keep positions stable
            return {}

        return _Req(run)


class FakeService:
    def __init__(self):
        self.status = {
            "old": {
                "privacyStatus": "public",
                "uploadStatus": "processed",
                "license": "youtube",
                "selfDeclaredMadeForKids": False,
            },
            "new": {"privacyStatus": "unlisted"},
        }
        self.items = {"PL1": ["a", "old"], "PL2": ["old", "old"], "PL3": ["b"]}
        self.updates = []
        self.fail_update = False

    def videos(self):
        return _Videos(self)

    def playlists(self):
        return _Playlists(self)

    def playlistItems(self):
        return _Items(self)


def test_privacy_change_keeps_the_other_writable_status_fields():
    svc = FakeService()

    update_video_status("old", privacy_status="private", service=svc)

    assert svc.updates[-1]["status"] == {
        "privacyStatus": "private",
        "license": "youtube",
        "selfDeclaredMadeForKids": False,
    }  # uploadStatus is read-only and must not be sent back


def test_an_unknown_privacy_is_refused_before_any_call():
    svc = FakeService()
    with pytest.raises(ValueError, match="privacy_status"):
        update_video_status("old", privacy_status="hidden", service=svc)
    assert not svc.updates


def test_playlist_membership_helpers():
    svc = FakeService()
    assert playlists_containing("old", service=svc) == ["PL1", "PL2"]
    assert remove_from_playlist("old", "PL2", service=svc) == 2
    assert playlists_containing("old", service=svc) == ["PL1"]


def test_supersede_moves_playlists_then_retires_the_old_upload():
    svc = FakeService()

    out = supersede("old", "new", service=svc)

    assert out["playlists"] == [
        {"playlist_id": "PL1", "added_new": True, "removed_old": 1},
        {"playlist_id": "PL2", "added_new": True, "removed_old": 2},
    ]
    assert [v for v in svc.items["PL1"] if v] == ["a", "new"]
    assert [v for v in svc.items["PL2"] if v] == ["new"]
    assert svc.items["PL3"] == ["b"]
    assert svc.status["old"]["privacyStatus"] == "private"
    assert svc.status["new"]["privacyStatus"] == "unlisted"  # untouched


def test_supersede_is_safe_to_re_run():
    svc = FakeService()
    supersede("old", "new", service=svc)

    again = supersede("old", "new", service=svc)

    assert again["playlists"] == []  # old is in no playlist any more
    assert [v for v in svc.items["PL1"] if v] == ["a", "new"]  # no duplicate


def test_a_failed_privacy_change_leaves_the_new_video_in_place():
    svc = FakeService()
    svc.fail_update = True

    with pytest.raises(RuntimeError):
        supersede("old", "new", service=svc)

    # playlists were already moved; the old video is still public, re-run fixes it
    assert "new" in svc.items["PL1"] and "old" not in svc.items["PL1"]
    svc.fail_update = False
    supersede("old", "new", service=svc)
    assert svc.status["old"]["privacyStatus"] == "private"


def test_supersede_refuses_the_same_video():
    with pytest.raises(ValueError):
        supersede("x", "x", service=FakeService())

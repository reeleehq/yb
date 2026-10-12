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
                    {
                        "id": f"{playlistId}:{n}",
                        "snippet": {"position": pos},
                        "contentDetails": {"videoId": v},
                    }
                    for pos, (n, v) in enumerate(
                        (n, v) for n, v in enumerate(rows) if v is not None
                    )
                ]
            }
        )

    def insert(self, *, part, body):
        pid = body["snippet"]["playlistId"]
        pos = body["snippet"].get("position")

        def run():
            vid = body["snippet"]["resourceId"]["videoId"]
            if pos is None:
                self.svc.items[pid].append(vid)
                return {"id": "new"}
            if pid in self.svc.auto_sorted:
                raise RuntimeError("manualSortRequired")
            live = [n for n, v in enumerate(self.svc.items[pid]) if v is not None]
            at = live[pos] if pos < len(live) else len(self.svc.items[pid])
            self.svc.items[pid].insert(at, vid)
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
            "new": {"privacyStatus": "unlisted", "uploadStatus": "processed"},
        }
        self.auto_sorted: set[str] = set()
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
        {"playlist_id": "PL1", "added_new": True, "position": 1, "removed_old": 1},
        {"playlist_id": "PL2", "added_new": True, "position": 0, "removed_old": 2},
    ]
    # the new video takes the old one's place, not the end of the list
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


def test_the_new_video_takes_the_old_ones_position():
    svc = FakeService()
    svc.items = {"PL1": ["a", "old", "b"]}

    out = supersede("old", "new", service=svc)

    assert [v for v in svc.items["PL1"] if v] == ["a", "new", "b"]
    assert out["playlists"][0]["position"] == 1


def test_an_auto_sorted_playlist_falls_back_to_append():
    svc = FakeService()
    svc.items = {"PL1": ["a", "old", "b"]}
    svc.auto_sorted = {"PL1"}

    out = supersede("old", "new", service=svc)

    assert [v for v in svc.items["PL1"] if v] == ["a", "b", "new"]
    assert out["playlists"][0]["position"] is None


def test_retiring_a_scheduled_video_clears_its_schedule():
    """Review of #23: a private video with a future publishAt, made private
    again, would still have gone public at that time."""
    svc = FakeService()
    svc.status["old"] = {
        "privacyStatus": "private",
        "publishAt": "2030-01-01T00:00:00Z",
    }

    supersede("old", "new", service=svc)

    assert "publishAt" not in svc.status["old"]
    update_video_status("new", privacy_status="private", service=svc)
    svc.status["new"]["publishAt"] = "2030-01-01T00:00:00Z"
    update_video_status(
        "new", privacy_status="private", keep_schedule=True, service=svc
    )
    assert svc.status["new"]["publishAt"] == "2030-01-01T00:00:00Z"


@pytest.mark.parametrize("upload_status", ["uploaded", "failed", "rejected", None])
def test_nothing_changes_when_the_new_upload_is_not_processed(upload_status):
    svc = FakeService()
    svc.status["new"] = {"privacyStatus": "unlisted", "uploadStatus": upload_status}
    before = {k: list(v) for k, v in svc.items.items()}

    with pytest.raises(ValueError, match="not processed"):
        supersede("old", "new", service=svc)

    assert svc.items == before and not svc.updates


def test_supersede_can_publish_the_new_video_first():
    svc = FakeService()

    supersede("old", "new", new_privacy="public", service=svc)

    assert svc.status["new"]["privacyStatus"] == "public"
    assert [b["id"] for b in svc.updates] == ["new", "old"]

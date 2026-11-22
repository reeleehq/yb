"""Tests for ``yb.config`` defaults and ``yb.youtube.playlists`` logic.

The playlist tests drive a tiny in-memory fake of the YouTube Data API service
(``playlists`` + ``playlistItems`` resources) so they run offline.
"""

import json

import pytest

from yb.config import YbConfig, load_config
from yb.youtube.playlists import (
    find_playlist,
    ensure_playlist,
    is_video_in_playlist,
    add_video_to_playlist,
)


# --- yb.config --------------------------------------------------------------


def test_config_builtin_defaults_when_no_file(tmp_path):
    cfg = load_config(tmp_path / "does_not_exist.json")
    assert cfg == YbConfig()
    assert cfg.privacy_status == "unlisted"
    assert cfg.playlist is None


def test_config_reads_file_and_ignores_unknown_keys(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"privacy_status": "private", "playlist": "TW Uploads", "bogus": 1})
    )
    cfg = load_config(path)
    assert cfg.privacy_status == "private"
    assert cfg.playlist == "TW Uploads"


def test_config_call_args_override_file(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"privacy_status": "private"}))
    # An explicit (non-None) override wins; None falls back to the file.
    assert load_config(path, privacy_status="public").privacy_status == "public"
    assert load_config(path, privacy_status=None).privacy_status == "private"


# --- fake YouTube service ---------------------------------------------------


class _Req:
    def __init__(self, result):
        self._result = result

    def execute(self):
        return self._result


class _Playlists:
    def __init__(self, store):
        self._store = store

    def list(self, *, part, mine, maxResults, pageToken=None):
        items = [
            {"id": pid, "snippet": {"title": t}, "status": {}}
            for pid, t in self._store.titles.items()
        ]
        return _Req({"items": items})  # single page is enough for tests

    def insert(self, *, part, body):
        pid = f"PL{len(self._store.titles) + 1}"
        self._store.titles[pid] = body["snippet"]["title"]
        self._store.items[pid] = []
        return _Req({"id": pid})


class _PlaylistItems:
    def __init__(self, store):
        self._store = store

    def list(self, *, part, playlistId, maxResults, pageToken=None):
        items = [
            {"contentDetails": {"videoId": v}}
            for v in self._store.items.get(playlistId, [])
        ]
        return _Req({"items": items})

    def insert(self, *, part, body):
        pid = body["snippet"]["playlistId"]
        vid = body["snippet"]["resourceId"]["videoId"]
        self._store.items.setdefault(pid, []).append(vid)
        return _Req({"id": "item1"})


class FakeService:
    def __init__(self):
        self.titles: dict[str, str] = {}
        self.items: dict[str, list[str]] = {}

    def playlists(self):
        return _Playlists(self)

    def playlistItems(self):
        return _PlaylistItems(self)


# --- yb.youtube.playlists ---------------------------------------------------


def test_find_playlist_missing_and_present():
    svc = FakeService()
    assert find_playlist("TW Uploads", service=svc) is None
    svc.titles["PLx"] = "TW Uploads"
    assert find_playlist("TW Uploads", service=svc) == "PLx"


def test_ensure_playlist_creates_when_missing():
    svc = FakeService()
    pid = ensure_playlist("TW Uploads", service=svc)
    assert pid in svc.titles and svc.titles[pid] == "TW Uploads"
    # Idempotent: a second ensure returns the same id, no duplicate.
    assert ensure_playlist("TW Uploads", service=svc) == pid
    assert list(svc.titles.values()).count("TW Uploads") == 1


def test_ensure_playlist_no_create_returns_none():
    svc = FakeService()
    assert ensure_playlist("Nope", create=False, service=svc) is None


def test_add_video_to_playlist_creates_and_is_idempotent():
    svc = FakeService()
    r1 = add_video_to_playlist("vid123", "TW Uploads", service=svc)
    assert r1["created"] is True and r1["added"] is True
    assert is_video_in_playlist("vid123", r1["playlist_id"], service=svc)

    # Re-adding the same video: playlist already exists, video already present.
    r2 = add_video_to_playlist("vid123", "TW Uploads", service=svc)
    assert r2["created"] is False and r2["added"] is False
    assert svc.items[r1["playlist_id"]] == ["vid123"]  # no duplicate


def test_add_video_to_playlist_no_create_raises():
    svc = FakeService()
    with pytest.raises(KeyError):
        add_video_to_playlist("vid", "Missing", create=False, service=svc)


class _NotFound(Exception):
    class resp:
        status = 404

    def __str__(self):
        return "HttpError 404 playlistNotFound"


def test_add_video_to_new_playlist_skips_list_and_retries_404(monkeypatch):
    """Regression (#75): a playlist just created 404s for a moment; no list, retry insert."""
    import yb.youtube.playlists as pl

    monkeypatch.setattr(pl.time, "sleep", lambda s: None)
    svc = FakeService()
    fails = {"n": 2}
    real_insert = _PlaylistItems.insert

    def flaky_insert(self, *, part, body):
        if fails["n"]:
            fails["n"] -= 1
            raise _NotFound()
        return real_insert(self, part=part, body=body)

    def no_list(self, **kw):
        raise AssertionError("presence check must be skipped for a new playlist")

    monkeypatch.setattr(_PlaylistItems, "insert", flaky_insert)
    monkeypatch.setattr(_PlaylistItems, "list", no_list)
    r = add_video_to_playlist("vid1", "Brand new", service=svc)
    assert r["created"] is True and r["added"] is True
    assert svc.items[r["playlist_id"]] == ["vid1"]

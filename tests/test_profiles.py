"""Profile selection: which config section, token file and channel check apply.

Offline: the YouTube service is a tiny fake exposing ``channels().list()``.
"""

import json

import pytest

from yb.config import load_config, resolve_profile
from yb.youtube.auth import (
    WrongChannel,
    check_channel,
    default_token_file,
)


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("YB_PROFILE", raising=False)


def test_default_profile_is_unchanged():
    assert resolve_profile(None) is None
    assert resolve_profile("default") is None
    assert default_token_file().name == "youtube_token.json"
    assert default_token_file("default").name == "youtube_token.json"


def test_named_profile_gets_its_own_token_file():
    assert default_token_file("reelee").name == "youtube_token.reelee.json"


def test_env_selects_profile_and_arg_wins(monkeypatch):
    monkeypatch.setenv("YB_PROFILE", "reelee")
    assert default_token_file().name == "youtube_token.reelee.json"
    assert default_token_file("other").name == "youtube_token.other.json"
    assert default_token_file("default").name == "youtube_token.json"


def _write_config(tmp_path, data):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data))
    return path


def test_profile_section_does_not_inherit_top_level(tmp_path):
    path = _write_config(
        tmp_path,
        {
            "playlist": "TW Uploads",
            "privacy_status": "private",
            "profiles": {"reelee": {"channel_id": "UC123"}},
        },
    )
    default = load_config(path)
    assert default.playlist == "TW Uploads" and default.channel_id is None
    reelee = load_config(path, profile="reelee")
    assert reelee.playlist is None
    assert reelee.privacy_status == "unlisted"
    assert reelee.channel_id == "UC123"


def test_unknown_profile_is_an_error(tmp_path):
    path = _write_config(tmp_path, {"profiles": {"a": {}}})
    with pytest.raises(KeyError, match="nope"):
        load_config(path, profile="nope")


def test_call_args_still_override_profile(tmp_path):
    path = _write_config(tmp_path, {"profiles": {"a": {"privacy_status": "private"}}})
    assert load_config(path, profile="a", privacy_status="public").privacy_status == (
        "public"
    )


class _Req:
    def __init__(self, result):
        self._result = result

    def execute(self):
        return self._result


class _Service:
    def __init__(self, items):
        self._items = items

    def channels(self):
        return self

    def list(self, **kwargs):
        return _Req({"items": self._items})


def _channel(cid="UC1", title="Reelee"):
    return [{"id": cid, "snippet": {"title": title, "customUrl": "@reelee-ai"}}]


def test_check_channel_returns_channel_and_accepts_match():
    info = check_channel(_Service(_channel()), "UC1")
    assert info == {"id": "UC1", "title": "Reelee", "handle": "@reelee-ai"}
    assert check_channel(_Service(_channel()))["id"] == "UC1"  # no expectation


def test_check_channel_rejects_mismatch():
    with pytest.raises(WrongChannel, match="UC999"):
        check_channel(_Service(_channel()), "UC999")


def test_publish_refuses_wrong_channel(tmp_path):
    from yb.youtube.publish import publish_video
    from yb.youtube.metadata import VideoMetadata

    path = _write_config(
        tmp_path, {"profiles": {"reelee": {"channel_id": "UC999"}}}
    )
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    cfg = load_config(path, profile="reelee")
    with pytest.raises(WrongChannel):
        publish_video(
            video,
            VideoMetadata(title="t", description="d"),
            config=cfg,
            service=_Service(_channel()),
        )

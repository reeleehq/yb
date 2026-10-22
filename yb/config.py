"""User configuration for ``yb`` publishing defaults.

Single source of truth for the publishing defaults you don't want to repeat on
every call — the privacy a new upload gets, and a playlist to drop every upload
into so you can find your videos later. The config lives next to the OAuth token
(``$XDG_CONFIG_HOME/yb/config.json`` or ``~/.config/yb/config.json``) so all of
``yb``'s persistent state sits in one directory.

The file is **optional**: with no file present the built-in defaults apply
(``privacy_status="unlisted"``, no playlist). Any subset of keys may be set;
unspecified keys fall back to the built-in defaults, and unknown keys are
ignored (forward-compatible).

Example ``~/.config/yb/config.json``::

    {
        "privacy_status": "unlisted",
        "playlist": "TW Uploads",
        "create_playlist_if_missing": true,
        "playlist_privacy_status": "private"
    }

**Profiles** publish to another YouTube channel/account. Each named profile has
its own OAuth token (``youtube_token.<profile>.json``) and its own section under
``"profiles"``. A profile starts from the built-in defaults, *not* from the
top-level keys (so a second channel never silently inherits your first
channel's playlist). Select one with ``profile=``, ``yb ... --profile NAME`` or
``$YB_PROFILE``; with none selected the top-level keys and ``youtube_token.json``
apply, exactly as before::

    {
        "privacy_status": "unlisted",
        "playlist": "TW Uploads",
        "profiles": {
            "reelee": {"privacy_status": "unlisted", "channel_id": "UC..."}
        }
    }

``channel_id`` (optional) is checked against the token's channel before any
upload, so a token minted for the wrong Google account fails loudly.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, fields
from pathlib import Path

PathLike = str | Path

#: Default privacy for a freshly uploaded video when neither the call nor the
#: config file specifies one. ``"unlisted"`` keeps videos off your public feed
#: but shareable by link until you deliberately make one ``"public"``.
DEFAULT_PRIVACY_STATUS = "unlisted"

#: Default privacy for a playlist that ``yb`` auto-creates. ``"private"`` means
#: only you see it — ideal for a personal "find my uploads" playlist.
DEFAULT_PLAYLIST_PRIVACY_STATUS = "private"


#: Environment variable naming the profile to use when none is passed.
PROFILE_ENV = "YB_PROFILE"


def resolve_profile(profile: str | None = None) -> str | None:
    """The active profile name: ``profile``, else ``$YB_PROFILE``, else ``None``.

    ``None`` (also for ``""`` and ``"default"``) is the default profile: the
    top-level config keys and ``youtube_token.json``.
    """
    name = profile if profile is not None else os.environ.get(PROFILE_ENV)
    return None if name in (None, "", "default") else name


def default_config_file() -> Path:
    """Config file location (``$XDG_CONFIG_HOME`` or ``~/.config``)."""
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base).expanduser() if base else Path.home() / ".config"
    return root / "yb" / "config.json"


@dataclass(frozen=True)
class YbConfig:
    """Resolved publishing defaults.

    Attributes:
        privacy_status: Privacy a new upload gets (``unlisted`` | ``private`` |
            ``public``) when the call doesn't override it.
        playlist: Title of a playlist every upload is added to (``None`` = none).
        create_playlist_if_missing: Create ``playlist`` if no playlist of that
            title exists yet, rather than erroring.
        playlist_privacy_status: Privacy for an auto-created playlist.
        channel_id: Channel the token must belong to (``None`` = don't check).
    """

    privacy_status: str = DEFAULT_PRIVACY_STATUS
    playlist: str | None = None
    create_playlist_if_missing: bool = True
    playlist_privacy_status: str = DEFAULT_PLAYLIST_PRIVACY_STATUS
    channel_id: str | None = None

    @classmethod
    def from_mapping(cls, mapping: dict | None) -> "YbConfig":
        """Build a config from a mapping, ignoring unknown keys."""
        mapping = mapping or {}
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in mapping.items() if k in known})


def load_config(
    config_file: PathLike | None = None,
    *,
    profile: str | None = None,
    **overrides,
) -> YbConfig:
    """Load publishing defaults from ``config_file`` (or the default location).

    A missing file yields the built-in defaults. ``overrides`` (typically the
    explicit keyword arguments a caller passed) take precedence when not
    ``None``, so call-site arguments always win over the file.

    ``profile`` (see :func:`resolve_profile`) picks the ``"profiles"`` section
    to read instead of the top-level keys; an unknown profile is an error.
    """
    profile = resolve_profile(profile)
    path = Path(config_file).expanduser() if config_file else default_config_file()
    data: dict = {}
    if path.exists():
        data = json.loads(path.read_text())
    if profile is not None:
        profiles = data.get("profiles") or {}
        if profile not in profiles:
            raise KeyError(
                f"No profile {profile!r} in {path} (known: {sorted(profiles) or 'none'}). "
                'Add it under "profiles" (see the yb-setup skill).'
            )
        data = dict(profiles[profile])
    data.update({k: v for k, v in overrides.items() if v is not None})
    return YbConfig.from_mapping(data)

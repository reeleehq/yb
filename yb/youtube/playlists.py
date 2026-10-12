"""YouTube playlist operations: find/create a playlist and add videos to it.

Wraps the Data API ``playlists`` and ``playlistItems`` resources (writable with
the ``youtube.force-ssl`` scope ``yb`` already requests — no extra consent). The
high-level :func:`add_video_to_playlist` works from a stable human *title* like
``"TW Uploads"``: it finds the playlist (optionally creating it), skips the add
if the video is already in it, and appends otherwise — so re-publishing or
re-running is idempotent.
"""

from __future__ import annotations

from yb.config import DEFAULT_PLAYLIST_PRIVACY_STATUS

_MAX_RESULTS = 50


def _service(**cred_kwargs):
    from yb.youtube.auth import get_service

    return get_service(**cred_kwargs)


def list_my_playlists(*, service=None, **cred_kwargs) -> list[dict]:
    """Return all playlists owned by the authenticated channel (paginated)."""
    service = service or _service(**cred_kwargs)
    out: list[dict] = []
    token = None
    while True:
        resp = (
            service.playlists()
            .list(
                part="snippet,status",
                mine=True,
                maxResults=_MAX_RESULTS,
                pageToken=token,
            )
            .execute()
        )
        out.extend(resp.get("items", []))
        token = resp.get("nextPageToken")
        if not token:
            return out


def find_playlist(title: str, *, service=None, **cred_kwargs) -> str | None:
    """Return the id of the caller's playlist titled ``title`` (or ``None``).

    Matches the first playlist with an exact title; YouTube allows duplicate
    titles, so prefer unique playlist names.
    """
    service = service or _service(**cred_kwargs)
    for pl in list_my_playlists(service=service):
        if pl["snippet"]["title"] == title:
            return pl["id"]
    return None


def create_playlist(
    title: str,
    *,
    description: str = "",
    privacy_status: str = DEFAULT_PLAYLIST_PRIVACY_STATUS,
    service=None,
    **cred_kwargs,
) -> str:
    """Create a playlist and return its id."""
    service = service or _service(**cred_kwargs)
    body = {
        "snippet": {"title": title, "description": description},
        "status": {"privacyStatus": privacy_status},
    }
    resp = service.playlists().insert(part="snippet,status", body=body).execute()
    return resp["id"]


def ensure_playlist(
    title: str,
    *,
    create: bool = True,
    description: str = "",
    privacy_status: str = DEFAULT_PLAYLIST_PRIVACY_STATUS,
    service=None,
    **cred_kwargs,
) -> str | None:
    """Return the id of the playlist titled ``title``, creating it if missing.

    Returns ``None`` only when the playlist is absent and ``create=False``.
    """
    service = service or _service(**cred_kwargs)
    pid = find_playlist(title, service=service)
    if pid:
        return pid
    if not create:
        return None
    return create_playlist(
        title, description=description, privacy_status=privacy_status, service=service
    )


def is_video_in_playlist(
    video_id: str, playlist_id: str, *, service=None, **cred_kwargs
) -> bool:
    """Whether ``video_id`` is already an item of ``playlist_id`` (paginated)."""
    service = service or _service(**cred_kwargs)
    token = None
    while True:
        resp = (
            service.playlistItems()
            .list(
                part="contentDetails",
                playlistId=playlist_id,
                maxResults=_MAX_RESULTS,
                pageToken=token,
            )
            .execute()
        )
        for it in resp.get("items", []):
            if it["contentDetails"]["videoId"] == video_id:
                return True
        token = resp.get("nextPageToken")
        if not token:
            return False


def add_to_playlist(
    video_id: str,
    playlist_id: str,
    *,
    position: int | None = None,
    service=None,
    **cred_kwargs,
) -> dict:
    """Add ``video_id`` to ``playlist_id`` (``playlistItems.insert``).

    Appended at the end, or inserted at the 0-based ``position`` when given
    (YouTube refuses a position on a playlist not sorted manually).
    """
    service = service or _service(**cred_kwargs)
    snippet = {
        "playlistId": playlist_id,
        "resourceId": {"kind": "youtube#video", "videoId": video_id},
    }
    if position is not None:
        snippet["position"] = position
    body = {"snippet": snippet}
    return service.playlistItems().insert(part="snippet", body=body).execute()


def add_video_to_playlist(
    video_id: str,
    title: str,
    *,
    create: bool = True,
    privacy_status: str = DEFAULT_PLAYLIST_PRIVACY_STATUS,
    skip_if_present: bool = True,
    service=None,
    **cred_kwargs,
) -> dict:
    """Find-or-create the playlist named ``title`` and append ``video_id``.

    Idempotent: with ``skip_if_present`` (default), a video already in the
    playlist is left alone instead of duplicated.

    Returns:
        ``{"playlist_id", "playlist_title", "added", "created"}`` where ``added``
        is ``False`` if the video was already present and ``created`` is ``True``
        if the playlist had to be made.

    Raises:
        KeyError: the playlist is absent and ``create=False``.
    """
    service = service or _service(**cred_kwargs)
    existing = find_playlist(title, service=service)
    if existing is None and not create:
        raise KeyError(f"Playlist not found and create=False: {title!r}")
    playlist_id = existing or create_playlist(
        title, privacy_status=privacy_status, service=service
    )
    created = existing is None

    if skip_if_present and is_video_in_playlist(video_id, playlist_id, service=service):
        added = False
    else:
        add_to_playlist(video_id, playlist_id, service=service)
        added = True

    return {
        "playlist_id": playlist_id,
        "playlist_title": title,
        "added": added,
        "created": created,
    }


def playlist_item_ids(
    video_id: str, playlist_id: str, *, service=None, **cred_kwargs
) -> list[str]:
    """The ``playlistItems`` ids holding ``video_id`` in ``playlist_id``.

    A list, because a video can sit in one playlist more than once.
    """
    service = service or _service(**cred_kwargs)
    return [item_id for item_id, _ in _items_of(video_id, playlist_id, service=service)]


def _items_of(video_id, playlist_id, *, service) -> list[tuple[str, int | None]]:
    """``(item id, position)`` of every occurrence of ``video_id``."""
    service = service or _service()
    out: list[tuple[str, int | None]] = []
    token = None
    while True:
        resp = (
            service.playlistItems()
            .list(
                part="snippet,contentDetails",
                playlistId=playlist_id,
                maxResults=_MAX_RESULTS,
                pageToken=token,
            )
            .execute()
        )
        out += [
            (it["id"], (it.get("snippet") or {}).get("position"))
            for it in resp.get("items", [])
            if it["contentDetails"]["videoId"] == video_id
        ]
        token = resp.get("nextPageToken")
        if not token:
            return out


def first_position(
    video_id: str, playlist_id: str, *, service=None, **cred_kwargs
) -> int | None:
    """The 0-based position of ``video_id``'s first occurrence (``None`` if absent)."""
    service = service or _service(**cred_kwargs)
    found = [
        p for _, p in _items_of(video_id, playlist_id, service=service) if p is not None
    ]
    return min(found) if found else None


def playlists_containing(video_id: str, *, service=None, **cred_kwargs) -> list[str]:
    """Ids of the authenticated channel's playlists that hold ``video_id``.

    Reads every item page of every playlist you own (1 quota unit per page),
    plus the ``playlists.list`` pages: on a large channel, budget for it.
    """
    service = service or _service(**cred_kwargs)
    return [
        pl["id"]
        for pl in list_my_playlists(service=service)
        if is_video_in_playlist(video_id, pl["id"], service=service)
    ]


def remove_from_playlist(
    video_id: str, playlist_id: str, *, service=None, **cred_kwargs
) -> int:
    """Remove every occurrence of ``video_id`` from ``playlist_id``.

    Returns how many items were removed (0 when it was not there).
    """
    service = service or _service(**cred_kwargs)
    ids = playlist_item_ids(video_id, playlist_id, service=service)
    for item_id in ids:
        service.playlistItems().delete(id=item_id).execute()
    return len(ids)

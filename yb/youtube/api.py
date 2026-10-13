"""YouTube video operations: get, upload, update metadata, thumbnail, chapters.

These wrap the YouTube Data API v3 ``videos``/``thumbnails`` resources for both
creating videos and *editing already-published ones* (titles, descriptions,
tags, languages, and chapter blocks in the description).
"""

from __future__ import annotations

import json
import re
import warnings
from pathlib import Path
from typing import Sequence

from mixing.chapters import Chapter
from yb.content import format_chapter_lines

PathLike = str | Path

_CHAPTERS_HEADER = "Chapters:"


def get_video(
    video_id: str, *, part: str = "snippet,status", service=None, **cred_kwargs
) -> dict:
    """Fetch a video resource (raises ``KeyError`` if not found/visible)."""
    service = service or _service(**cred_kwargs)
    items = service.videos().list(part=part, id=video_id).execute().get("items", [])
    if not items:
        raise KeyError(f"Video not found or not accessible: {video_id}")
    return items[0]


def upload_video(
    video_path: PathLike,
    body: dict,
    *,
    service=None,
    chunksize: int = 8 * 1024 * 1024,
    progress: bool = True,
    **cred_kwargs,
) -> dict:
    """Resumably upload a video with the given ``videos.insert`` ``body``.

    Returns the created video resource (includes ``id``).
    """
    from googleapiclient.http import MediaFileUpload

    service = service or _service(**cred_kwargs)
    media = MediaFileUpload(
        str(video_path), chunksize=chunksize, resumable=True, mimetype="video/*"
    )
    request = service.videos().insert(
        part=",".join(body.keys()), body=body, media_body=media
    )
    response = None
    while response is None:
        status, response = request.next_chunk()
        if progress and status:
            print(f"  upload {int(status.progress() * 100)}%")
    return response


def update_video(video_id: str, snippet: dict, *, service=None, **cred_kwargs) -> dict:
    """Update a video's snippet (``videos.update``). ``categoryId`` is required."""
    service = service or _service(**cred_kwargs)
    body = {"id": video_id, "snippet": snippet}
    return service.videos().update(part="snippet", body=body).execute()


def update_video_fields(
    video_id: str,
    *,
    title: str | None = None,
    description: str | None = None,
    tags: Sequence[str] | None = None,
    category_id: str | None = None,
    default_language: str | None = None,
    default_audio_language: str | None = None,
    service=None,
    **cred_kwargs,
) -> dict:
    """Patch selected snippet fields, preserving the rest.

    Fetches the current snippet, overlays the provided fields, and updates.
    ``categoryId`` must be present (kept from the existing snippet if not given).
    """
    service = service or _service(**cred_kwargs)
    snippet = dict(get_video(video_id, part="snippet", service=service)["snippet"])
    if title is not None:
        snippet["title"] = title
    if description is not None:
        snippet["description"] = description
    if tags is not None:
        snippet["tags"] = list(tags)
    if category_id is not None:
        snippet["categoryId"] = category_id
    if default_language is not None:
        snippet["defaultLanguage"] = default_language
    if default_audio_language is not None:
        snippet["defaultAudioLanguage"] = default_audio_language
    # videos.update replaces the snippet wholesale → keep only writable keys.
    writable = {
        k: snippet[k]
        for k in (
            "title",
            "description",
            "tags",
            "categoryId",
            "defaultLanguage",
            "defaultAudioLanguage",
        )
        if k in snippet
    }
    return update_video(video_id, writable, service=service)


#: Privacy values ``videos.update(part="status")`` accepts, least visible first.
PRIVACY_STATUSES = ("private", "unlisted", "public")


class VisibilityDropWarning(UserWarning):
    """:func:`supersede` leaves the re-cut less visible than the original was.

    Emitted before anything is changed, so escalating it refuses the call::

        warnings.simplefilter("error", VisibilityDropWarning)
    """


#: The ``status`` keys a ``videos.update`` may write. The part is replaced
#: wholesale, so everything else read back (``uploadStatus``, ``rejectionReason``,
#: ...) must be left out of the body, and these must be carried over.
_WRITABLE_STATUS_KEYS = (
    "privacyStatus",
    "embeddable",
    "license",
    "publicStatsViewable",
    "publishAt",
    "selfDeclaredMadeForKids",
    "containsSyntheticMedia",
)


def update_video_status(
    video_id: str,
    *,
    privacy_status: str | None = None,
    contains_synthetic_media: bool | None = None,
    keep_schedule: bool = False,
    service=None,
    **cred_kwargs,
) -> dict:
    """Change a video's privacy (or synthetic-media flag), keeping the rest.

    Read-modify-write of the ``status`` part (yb#19): ``videos.update`` replaces
    the part wholesale, so the current writable fields are carried over and
    only the ones given change. Making a video private never deletes it.

    Setting ``privacy_status`` clears a scheduled publish (``publishAt``):
    otherwise a video made private while scheduled would still go public at
    that time, and a past ``publishAt`` read back is refused by the API. Pass
    ``keep_schedule=True`` to keep it (only meaningful with ``"private"``).

    Raises:
        ValueError: ``privacy_status`` is not one of :data:`PRIVACY_STATUSES`.
    """
    if privacy_status is not None and privacy_status not in PRIVACY_STATUSES:
        raise ValueError(
            f"privacy_status must be one of {PRIVACY_STATUSES}, not {privacy_status!r}"
        )
    service = service or _service(**cred_kwargs)
    current = get_video(video_id, part="status", service=service).get("status", {})
    status = {k: current[k] for k in _WRITABLE_STATUS_KEYS if k in current}
    if privacy_status is not None:
        status["privacyStatus"] = privacy_status
        if not (keep_schedule and privacy_status == "private"):
            status.pop("publishAt", None)
    if contains_synthetic_media is not None:
        status["containsSyntheticMedia"] = contains_synthetic_media
    body = {"id": video_id, "status": status}
    return service.videos().update(part="status", body=body).execute()


def supersede(
    old_id: str,
    new_id: str,
    *,
    old_privacy: str = "private",
    new_privacy: str | None = None,
    move_playlists: bool = True,
    service=None,
    **cred_kwargs,
) -> dict:
    """Retire an upload that ``new_id`` replaces (yb#19).

    YouTube cannot replace a video's file, so a re-cut is a new upload. This
    puts the new one where the old one was and takes the old one out of view:

    0. refuses, before changing anything, unless ``new_id`` has finished
       processing (``uploadStatus == "processed"``): retiring the old video for
       a failed or rejected upload would leave the public neither;
    1. sets ``new_id`` to ``new_privacy`` when given (e.g. ``"public"``);
    2. for every playlist of yours that holds ``old_id`` (when
       ``move_playlists``): inserts ``new_id`` at the old one's position (or
       appends, if the playlist is not sorted manually), THEN removes
       ``old_id``, so a failure part-way never leaves a playlist with neither;
    3. sets ``old_id`` to ``old_privacy`` (default ``"private"``), clearing any
       scheduled publish. It is never deleted.

    The new video keeps its own privacy unless ``new_privacy`` is given, and an
    upload is ``unlisted`` by default: so the re-cut of a public video is NOT
    made public for you. When the result is less visible than the old video
    was (a public original, an unlisted re-cut), a :class:`VisibilityDropWarning`
    is emitted before anything changes; pass ``new_privacy="public"`` to publish
    the re-cut, or turn the warning into an error to refuse such calls.

    Captions and thumbnails are not copied: upload them with the new video
    (:func:`yb.youtube.publish_video`). Safe to re-run: every step checks
    before it acts. Quota: see :func:`yb.youtube.playlists_containing`; each
    write (insert, delete, update) is 50 units.

    Returns:
        ``{"old_id", "new_id", "playlists", "old_privacy", "new_privacy"}``
        where ``playlists`` lists ``{"playlist_id", "added_new", "position",
        "removed_old"}``.
    """
    from yb.youtube.playlists import (
        add_to_playlist,
        first_position,
        is_video_in_playlist,
        playlists_containing,
        remove_from_playlist,
    )

    if old_id == new_id:
        raise ValueError("supersede needs two different videos")
    for name, value in (("old_privacy", old_privacy), ("new_privacy", new_privacy)):
        if value is not None and value not in PRIVACY_STATUSES:
            raise ValueError(f"{name} must be one of {PRIVACY_STATUSES}, not {value!r}")
    service = service or _service(**cred_kwargs)
    new_status = get_video(new_id, part="status", service=service).get("status", {})
    if new_status.get("uploadStatus") != "processed":
        raise ValueError(
            f"new video {new_id} is not processed yet "
            f"(uploadStatus={new_status.get('uploadStatus')!r}); nothing was changed"
        )
    _warn_if_visibility_drops(
        old_id, new_id, new_status, old_privacy, new_privacy, service=service
    )
    if new_privacy is not None:
        update_video_status(new_id, privacy_status=new_privacy, service=service)
    moved = []
    if move_playlists:
        for pid in playlists_containing(old_id, service=service):
            added, position = False, None
            if not is_video_in_playlist(new_id, pid, service=service):
                position = first_position(old_id, pid, service=service)
                try:
                    add_to_playlist(new_id, pid, position=position, service=service)
                except Exception as e:
                    # Retry only the one refusal known to have inserted nothing:
                    # after a timeout the insert may have landed (yb#30).
                    if position is None or not _is_manual_sort_required(e):
                        raise
                    position = None
                    add_to_playlist(new_id, pid, service=service)
                added = True
            removed = remove_from_playlist(old_id, pid, service=service)
            moved.append(
                {
                    "playlist_id": pid,
                    "added_new": added,
                    "position": position,
                    "removed_old": removed,
                }
            )
    update_video_status(old_id, privacy_status=old_privacy, service=service)
    return {
        "old_id": old_id,
        "new_id": new_id,
        "playlists": moved,
        "old_privacy": old_privacy,
        "new_privacy": new_privacy,
    }


def _warn_if_visibility_drops(
    old_id, new_id, new_status, old_privacy, new_privacy, *, service
) -> None:
    """Warn when neither video ends up as visible as ``old_id`` is now (yb#30)."""
    try:
        old_status = get_video(old_id, part="status", service=service)["status"]
    except Exception:  # noqa: BLE001 - only a warning: never a new failure
        return  # a missing video is reported by the retire step, as before
    before = old_status.get("privacyStatus")
    new_after = new_privacy or new_status.get("privacyStatus")
    if before not in PRIVACY_STATUSES or new_after not in PRIVACY_STATUSES:
        return
    rank = PRIVACY_STATUSES.index
    if max(rank(new_after), rank(old_privacy)) >= rank(before):
        return
    scheduled = new_status.get("publishAt") if new_privacy is None else None
    when = f", scheduled to publish at {scheduled}" if scheduled else ""
    warnings.warn(
        f"supersede: {old_id} is {before} and will become {old_privacy}, while "
        f"its replacement {new_id} stays {new_after}{when}. Pass "
        f"new_privacy={before!r} to give the re-cut the original's visibility.",
        VisibilityDropWarning,
        stacklevel=3,
    )


def _is_manual_sort_required(error: Exception) -> bool:
    """Whether ``error`` is YouTube's ``manualSortRequired`` refusal.

    Reads the reasons from a googleapiclient ``HttpError``: both its
    ``error_details`` and the ``errors`` of its JSON ``content`` (the former
    may hold the body's ``details`` instead), falling back to the message.
    """
    reasons = [
        d.get("reason")
        for d in getattr(error, "error_details", None) or []
        if isinstance(d, dict)
    ]
    content = getattr(error, "content", None)
    if content:
        try:
            errors = json.loads(content)["error"]["errors"]
            reasons += [d.get("reason") for d in errors if isinstance(d, dict)]
        except (ValueError, TypeError, KeyError, AttributeError):
            pass
    return "manualSortRequired" in reasons or "manualSortRequired" in str(error)


def set_thumbnail(
    video_id: str, image_path: PathLike, *, service=None, **cred_kwargs
) -> dict:
    """Set a custom thumbnail (``thumbnails.set``)."""
    from googleapiclient.http import MediaFileUpload

    service = service or _service(**cred_kwargs)
    media = MediaFileUpload(str(image_path), mimetype="image/jpeg", resumable=False)
    return service.thumbnails().set(videoId=video_id, media_body=media).execute()


def set_chapters(
    video_id: str,
    chapters: Sequence[Chapter],
    *,
    header: str = _CHAPTERS_HEADER,
    service=None,
    **cred_kwargs,
) -> dict:
    """Insert/replace a chapters block in the video's description.

    Strips any prior block under ``header`` and appends the new one. YouTube
    renders interactive chapters when the first timestamp is ``0:00``.
    """
    service = service or _service(**cred_kwargs)
    snippet = get_video(video_id, part="snippet", service=service)["snippet"]
    new_desc = _replace_chapters_block(snippet.get("description", ""), chapters, header)
    return update_video_fields(video_id, description=new_desc, service=service)


def _replace_chapters_block(
    description: str, chapters: Sequence[Chapter], header: str
) -> str:
    """Return ``description`` with its chapters block replaced (or appended)."""
    # Remove an existing "<header> ... " block (header line + following ts lines).
    pattern = re.compile(
        rf"\n*{re.escape(header)}\n(?:\s*\d{{1,2}}(?::\d{{2}}){{1,2}}\s+.*\n?)+",
        re.MULTILINE,
    )
    base = pattern.sub("", description).rstrip()
    if not chapters:
        return base
    block = format_chapter_lines(chapters)
    return f"{base}\n\n{header}\n{block}" if base else f"{header}\n{block}"


def _service(**cred_kwargs):
    from yb.youtube.auth import get_service

    return get_service(**cred_kwargs)

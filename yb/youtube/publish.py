"""High-level YouTube publishing: prepare → upload → captions → thumbnail.

Two entry points:
    - :func:`publish_content` — given a prepared
      :class:`yb.content.PublicationContent`, upload it with captions,
      thumbnail, and chapters (in the description).
    - :func:`prepare_and_publish` — the one-call path: transcribe/derive
      metadata/detect chapters (via :func:`yb.content.prepare_content`) and
      upload, all from a media path.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from yb.config import YbConfig, load_config
from yb.content import PublicationContent, prepare_content
from yb.youtube.auth import check_channel, get_service
from yb.youtube.metadata import VideoMetadata, CATEGORY_SCIENCE_TECH
from yb.youtube.api import upload_video, set_thumbnail
from yb.youtube.captions import CaptionTrack, upsert_caption
from yb.youtube.playlists import add_video_to_playlist

PathLike = str | Path

#: Sentinel marking "argument not given — fall back to the config default".
#: Distinguishes an unset playlist (use config) from an explicit ``None``
#: (publish without adding to any playlist).
_USE_CONFIG = object()


class PartialPublish(RuntimeError):
    """The video was uploaded, then a later step failed (yb#21).

    The upload is the expensive step (1,600 quota units); captions, thumbnail
    and playlist can each fail afterwards on quota, auth or a transient error.
    Raising the bare error lost the new video's id, and a re-run uploaded a
    second copy. This carries what was done instead:

    - ``result``: the dict the publish call would have returned, as far as it
      got (``video_id``, ``url``, ``captions`` attached so far, ``thumbnail``,
      ``playlist``). Persist it.
    - ``step``: the step that failed, e.g. ``"caption ja"``.
    - ``__cause__``: the original error.

    Finish later without re-uploading: pass ``resume=err.result`` to the same
    call (:func:`publish_video` or :func:`publish_content`; for
    :func:`prepare_and_publish`, call :func:`publish_content` with the content
    it prepared, rather than preparing it again). Steps already done are
    skipped. A resume trusts the saved result: it does not upload, so new
    metadata, video path or privacy in the resuming call are ignored, and the
    remaining steps target the saved ``video_id``.

    ``result`` is plain JSON-able data, and the exception pickles (so a worker
    process can hand it back); ``__cause__`` does not survive pickling.
    """

    def __init__(self, result: dict, *, step: str, error: BaseException | None):
        self.result = result
        self.step = step
        super().__init__(
            f"Uploaded {result['video_id']} ({result['url']}), then {step!r} "
            f"failed: {error!r}. Nothing was lost: pass resume=err.result to "
            "finish without uploading again."
        )

    def __reduce__(self):
        return (_restore_partial, (self.result, self.step, str(self)))


def _restore_partial(result: dict, step: str, message: str) -> PartialPublish:
    """Unpickle a :class:`PartialPublish` without re-running ``__init__``."""
    err = PartialPublish.__new__(PartialPublish)
    RuntimeError.__init__(err, message)
    err.result, err.step = result, step
    return err


#: One post-upload step: ``(kind, key, run)``. ``kind`` is ``"caption"``,
#: ``"thumbnail"`` or ``"playlist"``; ``key`` the caption language (else "").
_Step = tuple[str, str, Callable[[], Any]]


def _step_done(result: Mapping, kind: str, key: str, nth: int = 1) -> bool:
    """Whether the saved ``result`` records this step; ``nth`` counts tracks
    in the same language, so a second ``"en"`` needs ``"en"`` recorded twice
    (yb#30)."""
    if kind == "caption":
        return result["captions"].count(key) >= nth
    if kind == "thumbnail":
        return bool(result["thumbnail"])
    return result["playlist"] is not None


def _after_upload(
    result: dict, steps: Sequence[_Step], *, resuming: bool = False
) -> dict:
    """Run the post-upload steps in order, recording each as it succeeds.

    A failing step raises :class:`PartialPublish` carrying ``result`` as far as
    it got. When ``resuming``, a step the saved ``result`` already records is
    skipped; a fresh run skips nothing (two tracks in one language both reach
    YouTube, the last one winning, as before).
    """
    done = (
        {
            "captions": list(result["captions"]),
            "thumbnail": result["thumbnail"],
            "playlist": result["playlist"],
        }
        if resuming
        else None
    )
    seen: Counter = Counter()
    for kind, key, run in steps:
        seen[kind, key] += 1
        if done is not None and _step_done(done, kind, key, seen[kind, key]):
            continue
        try:
            out = run()
        except Exception as e:
            raise PartialPublish(result, step=f"{kind} {key}".strip(), error=e) from e
        if kind == "caption":
            result["captions"].append(key)
        elif kind == "thumbnail":
            result["thumbnail"] = True
        else:
            result["playlist"] = out
    return result


def _upload_or_resume(
    resume: Mapping | None, upload: Callable[[], dict], privacy_status: str
) -> dict:
    """The starting result: a fresh upload's, or a copy of ``resume``'s."""
    if resume is not None:
        if not resume.get("video_id"):
            raise ValueError("resume= needs the result of an earlier publish call")
        # Rebuilt from the known fields, so a hand-built or partial dict gets
        # defaults (not a KeyError after the fact) and extra keys a caller
        # saved alongside do not leak into the return value.
        out = _result(
            resume["video_id"],
            resume.get("privacy_status", privacy_status),
            list(resume.get("captions") or []),
            bool(resume.get("thumbnail")),
            resume.get("playlist"),
        )
        return out
    resp = upload()
    actual_privacy = resp.get("status", {}).get("privacyStatus", privacy_status)
    return _result(resp["id"], actual_privacy, [], False)


def _maybe_add_to_playlist(
    video_id: str, playlist, cfg: YbConfig, *, service, progress: bool
) -> dict | None:
    """Add ``video_id`` to ``playlist`` (a title, or the config default)."""
    title = cfg.playlist if playlist is _USE_CONFIG else playlist
    if not title:
        return None
    if progress:
        print(f"  adding to playlist: {title!r}")
    return add_video_to_playlist(
        video_id,
        title,
        create=cfg.create_playlist_if_missing,
        privacy_status=cfg.playlist_privacy_status,
        service=service,
    )


def publish_content(
    content: PublicationContent,
    *,
    privacy_status: str | None = None,
    playlist=_USE_CONFIG,
    category_id: str = CATEGORY_SCIENCE_TECH,
    with_chapters: bool = True,
    attach_caption: bool = True,
    set_thumb: bool = True,
    config: YbConfig | None = None,
    client_secrets_file: PathLike | None = None,
    token_file: PathLike | None = None,
    profile: str | None = None,
    progress: bool = True,
    service=None,
    resume: Mapping | None = None,
    **cred_kwargs,
) -> dict:
    """Upload a prepared :class:`PublicationContent` to YouTube.

    Maps the content to a YouTube snippet (chapters embedded in the
    description when present), uploads, attaches the SRT caption track
    (language = ``content.audio_language`` or ``content.language``) and the
    thumbnail when available, and adds the video to the configured playlist.

    ``privacy_status`` and ``playlist`` default to your ``yb`` config (see
    :mod:`yb.config`): unset means "use the config value", so privacy falls back
    to ``unlisted`` and the video joins your configured playlist. Pass
    ``playlist=None`` to skip the playlist for one call, or ``playlist="Name"``
    to override the target.

    ``profile`` publishes as a named account/channel (own token and config
    section; see :mod:`yb.config`); ``None`` uses ``$YB_PROFILE`` or the default.

    ``cred_kwargs`` reach :func:`~yb.youtube.auth.get_credentials` (e.g.
    ``open_browser=False, port=8080`` for headless consent).

    Returns:
        ``{"video_id", "url", "studio_url", "privacy_status", "captions",
        "thumbnail", "playlist"}``. ``privacy_status`` reflects what YouTube
        actually set (an unaudited project may force ``"private"``); ``playlist``
        is the :func:`~yb.youtube.playlists.add_video_to_playlist` result or
        ``None``.

    Raises:
        PartialPublish: the upload succeeded and a later step failed;
            ``err.result`` holds the video id and what was done. Pass
            ``resume=err.result`` to finish without uploading again (yb#21).
    """
    cfg = config or load_config(profile=profile, privacy_status=privacy_status)
    privacy_status = cfg.privacy_status
    service = service or get_service(
        client_secrets_file=client_secrets_file,
        token_file=token_file,
        profile=profile,
        **cred_kwargs,
    )
    if cfg.channel_id:  # refuse to upload to the wrong account's channel
        check_channel(service, cfg.channel_id)
    meta = VideoMetadata.from_content(
        content, category_id=category_id, with_chapters=with_chapters
    )
    body = meta.insert_body(privacy_status=privacy_status)

    def upload():
        if progress:
            print(f"Uploading {content.media.name!r} as {privacy_status}...")
        return upload_video(content.media, body, service=service, progress=progress)

    result = _upload_or_resume(resume, upload, privacy_status)
    video_id = result["video_id"]

    steps: list[_Step] = []
    cap_lang = content.audio_language or content.language
    if (
        attach_caption
        and content.srt_path
        and Path(content.srt_path).exists()
        and cap_lang
    ):

        def caption():
            if progress:
                print(f"  attaching caption: {cap_lang}")
            upsert_caption(
                video_id,
                content.srt_path,
                language=cap_lang,
                name=_lang_name(cap_lang),
                service=service,
            )

        steps.append(("caption", cap_lang, caption))

    if set_thumb and content.thumbnail and Path(content.thumbnail).exists():

        def thumb():
            if progress:
                print("  setting thumbnail")
            set_thumbnail(video_id, content.thumbnail, service=service)

        steps.append(("thumbnail", "", thumb))

    steps.append(
        (
            "playlist",
            "",
            lambda: _maybe_add_to_playlist(
                video_id, playlist, cfg, service=service, progress=progress
            ),
        )
    )
    return _after_upload(result, steps, resuming=resume is not None)


def prepare_and_publish(
    media: PathLike,
    *,
    language: str = "English",
    language_code: str | None = None,
    audio_language_code: str | None = None,
    brand: str | None = None,
    extra_context: str | None = None,
    with_chapters: bool = True,
    with_thumbnail: bool = True,
    privacy_status: str | None = None,
    playlist=_USE_CONFIG,
    category_id: str = CATEGORY_SCIENCE_TECH,
    config: YbConfig | None = None,
    client_secrets_file: PathLike | None = None,
    token_file: PathLike | None = None,
    profile: str | None = None,
    progress: bool = True,
    **cred_kwargs,
) -> dict:
    """One call: prepare publication content from ``media`` and upload it.

    Transcribes (persisting the SRT next to the media) if needed, writes
    LLM metadata, detects chapters, renders a thumbnail, then uploads with
    captions + thumbnail + chapters and adds the video to the configured
    playlist. ``privacy_status`` and ``playlist`` default to your ``yb`` config
    (see :func:`publish_content`).

    ``profile`` publishes as a named account/channel (own token and config
    section; see :mod:`yb.config`); ``None`` uses ``$YB_PROFILE`` or the default.

    ``cred_kwargs`` reach :func:`~yb.youtube.auth.get_credentials` (e.g.
    ``open_browser=False, port=8080`` for headless consent).
    """
    content = prepare_content(
        media,
        language=language,
        language_code=language_code,
        audio_language_code=audio_language_code,
        brand=brand,
        extra_context=extra_context,
        with_chapters=with_chapters,
        with_thumbnail=with_thumbnail,
    )
    return publish_content(
        content,
        privacy_status=privacy_status,
        playlist=playlist,
        category_id=category_id,
        with_chapters=with_chapters,
        config=config,
        client_secrets_file=client_secrets_file,
        token_file=token_file,
        profile=profile,
        progress=progress,
        **cred_kwargs,
    )


def publish_video(
    video_path: PathLike,
    metadata: VideoMetadata,
    *,
    privacy_status: str | None = None,
    playlist=_USE_CONFIG,
    captions: Sequence[CaptionTrack] | None = None,
    thumbnail: PathLike | None = None,
    config: YbConfig | None = None,
    client_secrets_file: PathLike | None = None,
    token_file: PathLike | None = None,
    profile: str | None = None,
    progress: bool = True,
    service=None,
    resume: Mapping | None = None,
    **cred_kwargs,
) -> dict:
    """Lower-level upload: explicit :class:`VideoMetadata` + caption tracks.

    ``privacy_status`` and ``playlist`` default to your ``yb`` config (see
    :func:`publish_content`).

    If a step after the upload fails, :class:`PartialPublish` is raised with
    the new video's id and what was done so far (``err.result``). Pass
    ``resume=err.result`` to finish without uploading again (yb#21).

    ``profile`` publishes as a named account/channel (own token and config
    section; see :mod:`yb.config`); ``None`` uses ``$YB_PROFILE`` or the default.

    ``cred_kwargs`` reach :func:`~yb.youtube.auth.get_credentials` (e.g.
    ``open_browser=False, port=8080`` for headless consent).
    """
    cfg = config or load_config(profile=profile, privacy_status=privacy_status)
    privacy_status = cfg.privacy_status
    service = service or get_service(
        client_secrets_file=client_secrets_file,
        token_file=token_file,
        profile=profile,
        **cred_kwargs,
    )
    if cfg.channel_id:  # refuse to upload to the wrong account's channel
        check_channel(service, cfg.channel_id)
    body = metadata.insert_body(privacy_status=privacy_status)

    def upload():
        if progress:
            print(f"Uploading {Path(video_path).name!r} as {privacy_status}...")
        return upload_video(video_path, body, service=service, progress=progress)

    result = _upload_or_resume(resume, upload, privacy_status)
    video_id = result["video_id"]

    def caption(cap: CaptionTrack):
        def run():
            if progress:
                print(f"  attaching caption: {cap.name or cap.language}")
            upsert_caption(video_id, cap, service=service)

        return run

    steps: list[_Step] = [
        ("caption", cap.language, caption(cap)) for cap in captions or []
    ]
    if thumbnail and Path(thumbnail).exists():
        steps.append(
            (
                "thumbnail",
                "",
                lambda: set_thumbnail(video_id, thumbnail, service=service),
            )
        )
    steps.append(
        (
            "playlist",
            "",
            lambda: _maybe_add_to_playlist(
                video_id, playlist, cfg, service=service, progress=progress
            ),
        )
    )
    return _after_upload(result, steps, resuming=resume is not None)


def _result(video_id, privacy, captions, thumb, playlist=None) -> dict:
    return {
        "video_id": video_id,
        "url": f"https://youtu.be/{video_id}",
        "studio_url": f"https://studio.youtube.com/video/{video_id}/edit",
        "privacy_status": privacy,
        "captions": captions,
        "thumbnail": thumb,
        "playlist": playlist,
    }


def _lang_name(code: str) -> str:
    return {
        "en": "English",
        "fr": "Français",
        "es": "Español",
        "de": "Deutsch",
        "it": "Italiano",
        "pt": "Português",
        "ja": "日本語",
        "zh": "中文",
    }.get(code, code)

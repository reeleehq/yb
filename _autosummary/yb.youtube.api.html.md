# yb.youtube.api

YouTube video operations: get, upload, update metadata, thumbnail, chapters.

These wrap the YouTube Data API v3 `videos`/`thumbnails` resources for both
creating videos and *editing already-published ones* (titles, descriptions,
tags, languages, and chapter blocks in the description).

### Module Attributes

| [`PRIVACY_STATUSES`](#yb.youtube.api.PRIVACY_STATUSES)   | Privacy values `videos.update(part="status")` accepts.   |
|---------------------------------------------------------------------|----------------------------------------------------------|

### Functions

| [`get_video`](#yb.youtube.api.get_video)(video_id, \*[, part, service])           | Fetch a video resource (raises `KeyError` if not found/visible).      |
|-----------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------|
| [`set_chapters`](#yb.youtube.api.set_chapters)(video_id, chapters, \*[, ...])        | Insert/replace a chapters block in the video's description.           |
| [`set_thumbnail`](#yb.youtube.api.set_thumbnail)(video_id, image_path, \*[, service]) | Set a custom thumbnail (`thumbnails.set`).                            |
| [`supersede`](#yb.youtube.api.supersede)(old_id, new_id, \*[, old_privacy, ...])  | Retire an upload that `new_id` replaces (yb#19).                      |
| [`update_video`](#yb.youtube.api.update_video)(video_id, snippet, \*[, service])     | Update a video's snippet (`videos.update`).                           |
| [`update_video_fields`](#yb.youtube.api.update_video_fields)(video_id, \*[, title, ...])    | Patch selected snippet fields, preserving the rest.                   |
| [`update_video_status`](#yb.youtube.api.update_video_status)(video_id, \*[, ...])           | Change a video's privacy (or synthetic-media flag), keeping the rest. |
| [`upload_video`](#yb.youtube.api.upload_video)(video_path, body, \*[, service, ...]) | Resumably upload a video with the given `videos.insert` `body`.       |

### yb.youtube.api.PRIVACY_STATUSES *= ('private', 'unlisted', 'public')*

Privacy values `videos.update(part="status")` accepts.

### yb.youtube.api.get_video(video_id, , part='snippet,status', service=None, \*\*cred_kwargs)

Fetch a video resource (raises `KeyError` if not found/visible).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### yb.youtube.api.set_chapters(video_id, chapters, , header='Chapters:', service=None, \*\*cred_kwargs)

Insert/replace a chapters block in the video’s description.

Strips any prior block under `header` and appends the new one. YouTube
renders interactive chapters when the first timestamp is `0:00`.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### yb.youtube.api.set_thumbnail(video_id, image_path, , service=None, \*\*cred_kwargs)

Set a custom thumbnail (`thumbnails.set`).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### yb.youtube.api.supersede(old_id, new_id, , old_privacy='private', new_privacy=None, move_playlists=True, service=None, \*\*cred_kwargs)

Retire an upload that `new_id` replaces (yb#19).

YouTube cannot replace a video’s file, so a re-cut is a new upload. This
puts the new one where the old one was and takes the old one out of view:

1. refuses, before changing anything, unless `new_id` has finished
   processing (`uploadStatus == "processed"`): retiring the old video for
   a failed or rejected upload would leave the public neither;
2. sets `new_id` to `new_privacy` when given (e.g. `"public"`);
3. for every playlist of yours that holds `old_id` (when
   `move_playlists`): inserts `new_id` at the old one’s position (or
   appends, if the playlist is not sorted manually), THEN removes
   `old_id`, so a failure part-way never leaves a playlist with neither;
4. sets `old_id` to `old_privacy` (default `"private"`), clearing any
   scheduled publish. It is never deleted.

Captions and thumbnails are not copied: upload them with the new video
([`yb.youtube.publish_video()`](yb.youtube.html.md#yb.youtube.publish_video)). Safe to re-run: every step checks
before it acts. Quota: see [`yb.youtube.playlists_containing()`](yb.youtube.html.md#yb.youtube.playlists_containing); each
write (insert, delete, update) is 50 units.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)
* **Returns:**
  `{"old_id", "new_id", "playlists", "old_privacy", "new_privacy"}`
  where `playlists` lists `{"playlist_id", "added_new", "position",
  "removed_old"}`.

### yb.youtube.api.update_video(video_id, snippet, , service=None, \*\*cred_kwargs)

Update a video’s snippet (`videos.update`). `categoryId` is required.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### yb.youtube.api.update_video_fields(video_id, , title=None, description=None, tags=None, category_id=None, default_language=None, default_audio_language=None, service=None, \*\*cred_kwargs)

Patch selected snippet fields, preserving the rest.

Fetches the current snippet, overlays the provided fields, and updates.
`categoryId` must be present (kept from the existing snippet if not given).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### yb.youtube.api.update_video_status(video_id, , privacy_status=None, contains_synthetic_media=None, keep_schedule=False, service=None, \*\*cred_kwargs)

Change a video’s privacy (or synthetic-media flag), keeping the rest.

Read-modify-write of the `status` part (yb#19): `videos.update` replaces
the part wholesale, so the current writable fields are carried over and
only the ones given change. Making a video private never deletes it.

Setting `privacy_status` clears a scheduled publish (`publishAt`):
otherwise a video made private while scheduled would still go public at
that time, and a past `publishAt` read back is refused by the API. Pass
`keep_schedule=True` to keep it (only meaningful with `"private"`).

* **Raises:**
  [**ValueError**](https://docs.python.org/3/builtins/exceptions.html#ValueError) – `privacy_status` is not one of [`PRIVACY_STATUSES`](#yb.youtube.api.PRIVACY_STATUSES).
* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### yb.youtube.api.upload_video(video_path, body, , service=None, chunksize=8388608, progress=True, \*\*cred_kwargs)

Resumably upload a video with the given `videos.insert` `body`.

Returns the created video resource (includes `id`).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

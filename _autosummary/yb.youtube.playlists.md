# yb.youtube.playlists

YouTube playlist operations: find/create a playlist and add videos to it.

Wraps the Data API `playlists` and `playlistItems` resources (writable with
the `youtube.force-ssl` scope `yb` already requests — no extra consent). The
high-level [`add_video_to_playlist()`](#yb.youtube.playlists.add_video_to_playlist) works from a stable human *title* like
`"TW Uploads"`: it finds the playlist (optionally creating it), skips the add
if the video is already in it, and appends otherwise — so re-publishing or
re-running is idempotent.

### Functions

| [`add_to_playlist`](#yb.youtube.playlists.add_to_playlist)(video_id, playlist_id, \*[, ...])   | Add `video_id` to `playlist_id` (`playlistItems.insert`).                 |
|------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------|
| [`add_video_to_playlist`](#yb.youtube.playlists.add_video_to_playlist)(video_id, title, \*[, ...])   | Find-or-create the playlist named `title` and append `video_id`.          |
| [`create_playlist`](#yb.youtube.playlists.create_playlist)(title, \*[, description, ...])      | Create a playlist and return its id.                                      |
| [`ensure_playlist`](#yb.youtube.playlists.ensure_playlist)(title, \*[, create, ...])           | Return the id of the playlist titled `title`, creating it if missing.     |
| [`find_playlist`](#yb.youtube.playlists.find_playlist)(title, \*[, service])                 | Return the id of the caller's playlist titled `title` (or `None`).        |
| [`first_position`](#yb.youtube.playlists.first_position)(video_id, playlist_id, \*[, ...])    | The 0-based position of `video_id`'s first occurrence (`None` if absent). |
| [`is_video_in_playlist`](#yb.youtube.playlists.is_video_in_playlist)(video_id, playlist_id, \*)     | Whether `video_id` is already an item of `playlist_id` (paginated).       |
| [`list_my_playlists`](#yb.youtube.playlists.list_my_playlists)(\*[, service])                    | Return all playlists owned by the authenticated channel (paginated).      |
| [`playlist_item_ids`](#yb.youtube.playlists.playlist_item_ids)(video_id, playlist_id, \*)        | The `playlistItems` ids holding `video_id` in `playlist_id`.              |
| [`playlists_containing`](#yb.youtube.playlists.playlists_containing)(video_id, \*[, service])       | Ids of the authenticated channel's playlists that hold `video_id`.        |
| [`remove_from_playlist`](#yb.youtube.playlists.remove_from_playlist)(video_id, playlist_id, \*)     | Remove every occurrence of `video_id` from `playlist_id`.                 |

### yb.youtube.playlists.add_to_playlist(video_id, playlist_id, , position=None, service=None, \*\*cred_kwargs)

Add `video_id` to `playlist_id` (`playlistItems.insert`).

Appended at the end, or inserted at the 0-based `position` when given
(YouTube refuses a position on a playlist not sorted manually).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### yb.youtube.playlists.add_video_to_playlist(video_id, title, , create=True, privacy_status='private', skip_if_present=True, service=None, \*\*cred_kwargs)

Find-or-create the playlist named `title` and append `video_id`.

Idempotent: with `skip_if_present` (default), a video already in the
playlist is left alone instead of duplicated.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)
* **Returns:**
  `{"playlist_id", "playlist_title", "added", "created"}` where `added`
  is `False` if the video was already present and `created` is `True`
  if the playlist had to be made.
* **Raises:**
  [**KeyError**](https://docs.python.org/3/builtins/exceptions.html#KeyError) – the playlist is absent and `create=False`.

### yb.youtube.playlists.create_playlist(title, , description='', privacy_status='private', service=None, \*\*cred_kwargs)

Create a playlist and return its id.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### yb.youtube.playlists.ensure_playlist(title, , create=True, description='', privacy_status='private', service=None, \*\*cred_kwargs)

Return the id of the playlist titled `title`, creating it if missing.

Returns `None` only when the playlist is absent and `create=False`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### yb.youtube.playlists.find_playlist(title, , service=None, \*\*cred_kwargs)

Return the id of the caller’s playlist titled `title` (or `None`).

Matches the first playlist with an exact title; YouTube allows duplicate
titles, so prefer unique playlist names.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### yb.youtube.playlists.first_position(video_id, playlist_id, , service=None, \*\*cred_kwargs)

The 0-based position of `video_id`’s first occurrence (`None` if absent).

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### yb.youtube.playlists.is_video_in_playlist(video_id, playlist_id, , service=None, \*\*cred_kwargs)

Whether `video_id` is already an item of `playlist_id` (paginated).

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### yb.youtube.playlists.list_my_playlists(, service=None, \*\*cred_kwargs)

Return all playlists owned by the authenticated channel (paginated).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]

### yb.youtube.playlists.playlist_item_ids(video_id, playlist_id, , service=None, \*\*cred_kwargs)

The `playlistItems` ids holding `video_id` in `playlist_id`.

A list, because a video can sit in one playlist more than once.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### yb.youtube.playlists.playlists_containing(video_id, , service=None, \*\*cred_kwargs)

Ids of the authenticated channel’s playlists that hold `video_id`.

Reads every item page of every playlist you own (1 quota unit per page),
plus the `playlists.list` pages: on a large channel, budget for it.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### yb.youtube.playlists.remove_from_playlist(video_id, playlist_id, , service=None, \*\*cred_kwargs)

Remove every occurrence of `video_id` from `playlist_id`.

Returns how many items were removed (0 when it was not there).

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

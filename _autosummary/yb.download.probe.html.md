# yb.download.probe

Online checks for servers: do the configured cookies still get past YouTube?

A cookies file exported from an everyday browser session goes stale: YouTube
rotates the session cookies as a security measure, after which every client gets
“Sign in to confirm you’re not a bot”. [`check_cookies()`](#yb.download.probe.check_cookies) finds that out
before the first real download: it checks the file holds a logged-in session,
then reads one known public video with it, on a private copy so the check never
rewrites the file. [`check_po_token_server()`](#yb.download.probe.check_po_token_server) pings the PO-token provider’s
server. `yb check --online` runs both.

```pycon
>>> from yb.download.probe import check_cookies
>>> print("\n".join(check_cookies()) or "cookies ok")
```

### Module Attributes

| [`PROBE_VIDEO_URL`](#yb.download.probe.PROBE_VIDEO_URL)     | A public video that has stayed up since 2005 ("Me at the zoo").     |
|----------------------------------------------------------------------|---------------------------------------------------------------------|
| [`ROTATED_MARKER`](#yb.download.probe.ROTATED_MARKER)      | yt-dlp's wording when the cookies it was given stop authenticating. |
| [`BOT_WALL_MARKERS`](#yb.download.probe.BOT_WALL_MARKERS)    | yt-dlp's wording for YouTube's bot wall.                            |
| [`LOGIN_COOKIE`](#yb.download.probe.LOGIN_COOKIE)        | the login cookie plus one of the API session ids.                   |
| [`PING_TIMEOUT_S`](#yb.download.probe.PING_TIMEOUT_S)      | Seconds to wait for the PO-token server's `/ping`.                  |
| [`COOKIE_WIKI_URL`](#yb.download.probe.COOKIE_WIKI_URL)     | yt-dlp's guide to exporting YouTube cookies.                        |
| [`COOKIE_EXPORT_STEPS`](#yb.download.probe.COOKIE_EXPORT_STEPS) | How to export cookies the browser will not rotate.                  |

### Functions

| [`check_cookies`](#yb.download.probe.check_cookies)([cookies_file, probe_url, ...])   | Problems with the cookies downloads would use (empty when they work).          |
|--------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| [`check_po_token_server`](#yb.download.probe.check_po_token_server)([base_url, urlopen, ...]) | Problems reaching the PO-token provider's server (`GET <base_url>/ping`).      |
| [`configured_cookies`](#yb.download.probe.configured_cookies)([cookies_file])              | `(file, problem)`: the cookies file downloads would use, or why there is none. |
| [`logged_in_problem`](#yb.download.probe.logged_in_problem)(path)                         | Why `path` is not a logged-in YouTube session (unexpired), or `None`.          |

### yb.download.probe.BOT_WALL_MARKERS *= ("confirm you're not a bot", 'confirm you’re not a bot')*

yt-dlp’s wording for YouTube’s bot wall.

### yb.download.probe.COOKIE_EXPORT_STEPS *= 'Export them again so the browser never rotates them: open a private / incognito window, log in to YouTube, go to https://www.youtube.com/robots.txt in that same tab, export the youtube.com cookies in Netscape format (a cookies.txt extension), then close the private window right away and never reopen that session. See https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies'*

How to export cookies the browser will not rotate.

### yb.download.probe.COOKIE_WIKI_URL *= 'https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies'*

yt-dlp’s guide to exporting YouTube cookies.

### yb.download.probe.LOGIN_COOKIE *= 'LOGIN_INFO'*

the
login cookie plus one of the API session ids.

* **Type:**
  What makes a jar a logged-in YouTube session, by yt-dlp’s own rule

### yb.download.probe.PING_TIMEOUT_S *= 3*

Seconds to wait for the PO-token server’s `/ping`.

### yb.download.probe.PROBE_VIDEO_URL *= 'https://www.youtube.com/watch?v=jNQXAC9IVRw'*

A public video that has stayed up since 2005 (“Me at the zoo”).

### yb.download.probe.ROTATED_MARKER *= 'cookies are no longer valid'*

yt-dlp’s wording when the cookies it was given stop authenticating.

### yb.download.probe.check_cookies(cookies_file=None, \*, probe_url='https://www.youtube.com/watch?v=jNQXAC9IVRw', fetch_info=<function \_probe_info>)

Problems with the cookies downloads would use (empty when they work).

Checks that the file holds a logged-in session, then reads `probe_url`
with it (one metadata fetch; yt-dlp works on a copy, so the file is left as
it was). With no file configured there is nothing to check.

* **Parameters:**
  * **cookies_file** ([`Union`](https://docs.python.org/3/library/typing.html#typing.Union)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path), [`Literal`](https://docs.python.org/3/library/typing.html#typing.Literal)[[`False`](https://docs.python.org/3/builtins/constants.html#False)], [`None`](https://docs.python.org/3/builtins/constants.html#None)]) – As in [`download_youtube_video()`](yb.download.html.md#yb.download.download_youtube_video).
  * **probe_url** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – A public video every working setup can read.
  * **fetch_info** ([`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]) – `(url, *, cookies_file, extra_opts)` metadata fetcher; a
    fake in tests.
* **Returns:**
  no or a missing file where one was named,
  not a logged-in session, rotated or expired, refused by the bot check,
  or the probe failed for another reason.
* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### yb.download.probe.check_po_token_server(base_url='http://127.0.0.1:4416', \*, urlopen=<function urlopen>, timeout_s=3)

Problems reaching the PO-token provider’s server (`GET <base_url>/ping`).

The plugin alone does nothing: without its server, yt-dlp warns and carries
on without tokens.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### yb.download.probe.configured_cookies(cookies_file=None)

`(file, problem)`: the cookies file downloads would use, or why there is none.

`cookies_file` as in [`download_youtube_video()`](yb.download.html.md#yb.download.download_youtube_video). With
`None`, a `$YB_COOKIES_FILE` naming a missing file is a problem (downloads
would silently go anonymous); no file configured at all is not.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path) | [`None`](https://docs.python.org/3/builtins/constants.html#None), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)]

### yb.download.probe.logged_in_problem(path)

Why `path` is not a logged-in YouTube session (unexpired), or `None`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

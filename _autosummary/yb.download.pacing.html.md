# yb.download.pacing

Polite pacing for yt-dlp downloads, and a useful message when YouTube pushes back.

`pace="polite"` (or a [`Pace`](#yb.download.pacing.Pace)) maps to yt-dlp’s sleep and rate-limit
options, so a long playlist can be fetched without hammering YouTube. The
default everywhere is `pace=None`: no options are added and behaviour is
unchanged. A raw yt-dlp option in `extra_opts` still wins over a pace.

```pycon
>>> pace_opts("polite")["sleep_interval"]
20
>>> pace_opts(None)
{}
```

### Module Attributes

| [`PACE_PRESETS`](#yb.download.pacing.PACE_PRESETS)   | Named paces accepted wherever `pace=` is.   |
|-----------------------------------------------------------------|---------------------------------------------|

### Functions

| [`explain_rate_limit`](#yb.download.pacing.explain_rate_limit)()   | Re-raise yt-dlp errors that look like a block as [`RateLimitedError`](#yb.download.pacing.RateLimitedError).   |
|-------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------|
| [`pace_opts`](#yb.download.pacing.pace_opts)(pace)        | The yt-dlp options for `pace` (empty for `None`).                                                                     |
| [`parse_rate`](#yb.download.pacing.parse_rate)(rate)       | Parse a rate such as `"4M"` or `"500k"` into bytes per second.                                                        |
| [`resolve_pace`](#yb.download.pacing.resolve_pace)(pace)     | Turn a preset name, a [`Pace`](#yb.download.pacing.Pace) or `None` into a `Pace` (or `None`).      |

### Classes

| [`Pace`](#yb.download.pacing.Pace)([sleep_interval, max_sleep_interval, ...])   | How gently to talk to YouTube.   |
|----------------------------------------------------------------------------------------------------|----------------------------------|

### Exceptions

| [`RateLimitedError`](#yb.download.pacing.RateLimitedError)   | YouTube refused the request (HTTP 429 or a "confirm you're not a bot" wall).   |
|---------------------------------------------------------------------|--------------------------------------------------------------------------------|

### yb.download.pacing.PACE_PRESETS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Pace](#yb.download.pacing.Pace)]* *= {'polite': Pace(sleep_interval=20, max_sleep_interval=60, sleep_requests=1, limit_rate='4M')}*

Named paces accepted wherever `pace=` is.

### *class* yb.download.pacing.Pace(sleep_interval=None, max_sleep_interval=None, sleep_requests=None, limit_rate=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

How gently to talk to YouTube.

#### sleep_interval

Seconds to sleep before each download (yt-dlp
`sleep_interval`); with `max_sleep_interval` a random value in
between is used.

* **Type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### max_sleep_interval

Upper bound of the random sleep.

* **Type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### sleep_requests

Seconds to sleep between metadata requests
(yt-dlp `sleep_interval_requests`).

* **Type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### limit_rate

Maximum download rate, e.g. `"4M"` or `"500K"` (bytes/s).

* **Type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### *exception* yb.download.pacing.RateLimitedError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

YouTube refused the request (HTTP 429 or a “confirm you’re not a bot” wall).

### yb.download.pacing.explain_rate_limit()

Re-raise yt-dlp errors that look like a block as [`RateLimitedError`](#yb.download.pacing.RateLimitedError).

* **Return type:**
  [`Iterator`](https://docs.python.org/3/library/typing.html#typing.Iterator)[[`None`](https://docs.python.org/3/builtins/constants.html#None)]

### yb.download.pacing.pace_opts(pace)

The yt-dlp options for `pace` (empty for `None`).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### yb.download.pacing.parse_rate(rate)

Parse a rate such as `"4M"` or `"500k"` into bytes per second.

```pycon
>>> parse_rate("4M")
4194304
```

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

### yb.download.pacing.resolve_pace(pace)

Turn a preset name, a [`Pace`](#yb.download.pacing.Pace) or `None` into a `Pace` (or `None`).

* **Return type:**
  [`Pace`](#yb.download.pacing.Pace) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

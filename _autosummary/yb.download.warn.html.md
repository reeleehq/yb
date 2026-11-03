# yb.download.warn

Warnings attributed to the caller’s code, not to yb’s own plumbing.

A fixed `stacklevel` breaks whenever a call path gains a frame (a context
manager, a cache, a wrapper), and the warning then names `contextlib.py`.
[`warn_at_caller()`](#yb.download.warn.warn_at_caller) walks the stack to the first frame outside the given
files instead.

```pycon
>>> import warnings
>>> with warnings.catch_warnings(record=True) as got:
...     warnings.simplefilter("always")
...     warn_at_caller("careful")
>>> str(got[0].message)
'careful'
```

### Module Attributes

| [`PLUMBING_FILES`](#yb.download.warn.PLUMBING_FILES)   | this package and `contextlib`.   |
|-------------------------------------------------------------------|----------------------------------|

### Functions

| [`warn_at_caller`](#yb.download.warn.warn_at_caller)(message[, category, plumbing])   | `warnings.warn` at the first frame whose file does not start with `plumbing`.   |
|--------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------|

### yb.download.warn.PLUMBING_FILES *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('/home/runner/work/yb/yb/yb/download', '/opt/hostedtoolcache/Python/3.12.16/x64/lib/python3.12/contextlib.py')*

this package and `contextlib`.

* **Type:**
  Files whose frames are never the caller

### yb.download.warn.warn_at_caller(message, category=<class 'UserWarning'>, \*, plumbing=('/home/runner/work/yb/yb/yb/download', '/opt/hostedtoolcache/Python/3.12.16/x64/lib/python3.12/contextlib.py'))

`warnings.warn` at the first frame whose file does not start with `plumbing`.

Not Python 3.12’s `skip_file_prefixes`: the floor is 3.10, and on 3.12 it
still attributed a warning raised under a `contextlib` frame to
`contextlib.py` (`tests/test_download_cookies.py` pins the behaviour).

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

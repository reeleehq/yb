"""Warnings attributed to the caller's code, not to yb's own plumbing.

A fixed ``stacklevel`` breaks whenever a call path gains a frame (a context
manager, a cache, a wrapper), and the warning then names ``contextlib.py``.
:func:`warn_at_caller` walks the stack to the first frame outside the given
files instead.

    >>> import warnings
    >>> with warnings.catch_warnings(record=True) as got:
    ...     warnings.simplefilter("always")
    ...     warn_at_caller("careful")
    >>> str(got[0].message)
    'careful'
"""

from __future__ import annotations

import contextlib
import sys
import warnings
from pathlib import Path

#: Files whose frames are never the caller: this package and ``contextlib``.
PLUMBING_FILES: tuple[str, ...] = (str(Path(__file__).parent), contextlib.__file__)


def warn_at_caller(
    message: str,
    category: type[Warning] = UserWarning,
    *,
    plumbing: tuple[str, ...] = PLUMBING_FILES,
) -> None:
    """``warnings.warn`` at the first frame whose file does not start with ``plumbing``.

    Not Python 3.12's ``skip_file_prefixes``: the floor is 3.10, and on 3.12 it
    still attributed a warning raised under a ``contextlib`` frame to
    ``contextlib.py`` (``tests/test_download_cookies.py`` pins the behaviour).
    """
    frame, level = sys._getframe(1), 2
    while frame is not None and frame.f_code.co_filename.startswith(plumbing):
        frame, level = frame.f_back, level + 1
    warnings.warn(message, category, stacklevel=level)

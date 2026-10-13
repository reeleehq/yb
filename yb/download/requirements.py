"""Preflight for downloading: does yt-dlp have what YouTube now demands?

YouTube makes yt-dlp solve a JavaScript "n challenge". Without a solver it
fails late and cryptically (``No video formats found!``). Solving needs two
things:

- yt-dlp's challenge-solver scripts, shipped by ``yt-dlp[default]`` (the
  ``yt-dlp-ejs`` package), which ``yb[download]`` depends on;
- a JavaScript runtime. **Deno** is the one yt-dlp enables by default, and the
  one that works.

Deno's installer puts it in ``~/.deno/bin`` and only adds that to ``PATH`` for
interactive shells, so a cron job or service often can't see it. This module
also looks there, and :func:`yt_dlp_runtime_opts` hands yt-dlp the explicit
path, so downloads work without touching ``PATH``.

    >>> from yb.download import check_requirements
    >>> problems = check_requirements()  # doctest: +SKIP
    >>> print("\\n\\n".join(problems) or "ready")  # doctest: +SKIP

Nothing here raises: missing pieces are reported (and, by default, warned) with
the command that fixes them.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import warnings
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

#: The JavaScript runtime yt-dlp enables by default, and the one that works.
DENO = "deno"

#: Deno's official installer.
DENO_INSTALL_CMD = "curl -fsSL https://deno.land/install.sh | sh"

#: Env var Deno's installer honours for its install root (binary in ``<root>/bin``).
DENO_INSTALL_ENV = "DENO_INSTALL"

#: yt-dlp's import name.
YT_DLP_MODULE = "yt_dlp"

#: Module that carries yt-dlp's challenge-solver scripts (from ``yt-dlp[default]``).
EJS_MODULE = "yt_dlp_ejs"

#: yt-dlp's notes on the JavaScript challenge.
EJS_WIKI_URL = "https://github.com/yt-dlp/yt-dlp/wiki/EJS"

#: The yt-dlp option naming JS runtimes (``{"deno": {"path": ...}}``).
JS_RUNTIMES_OPT = "js_runtimes"


class DownloadRequirementWarning(UserWarning):
    """A download prerequisite (JS runtime, solver scripts) looks missing."""


@dataclass(frozen=True)
class JsRuntime:
    """A JavaScript runtime found for yt-dlp.

    Attributes:
        name: yt-dlp's key for the runtime (e.g. ``"deno"``).
        path: The executable.
        on_path: Whether yt-dlp would find it by name on ``PATH`` unaided.
    """

    name: str
    path: Path
    on_path: bool


def deno_search_dirs() -> tuple[Path, ...]:
    """Where Deno's installer puts the binary: ``$DENO_INSTALL/bin``, ``~/.deno/bin``."""
    dirs = []
    if root := os.environ.get(DENO_INSTALL_ENV):
        dirs.append(Path(root).expanduser() / "bin")
    dirs.append(Path.home() / ".deno" / "bin")
    return tuple(dict.fromkeys(dirs))


def find_js_runtime(
    *,
    which: Callable[[str], str | None] = shutil.which,
    search_dirs: Iterable[Path] | None = None,
) -> JsRuntime | None:
    """Find Deno on ``PATH``, else in its standard install location.

    Args:
        which: ``PATH`` lookup (injectable for tests).
        search_dirs: Extra directories to look in when it isn't on ``PATH``
            (default :func:`deno_search_dirs`).

    Returns:
        The runtime found, or ``None``.
    """
    if found := which(DENO):
        return JsRuntime(DENO, Path(found), on_path=True)
    dirs = deno_search_dirs() if search_dirs is None else search_dirs
    for d in dirs:
        candidate = Path(d) / DENO
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return JsRuntime(DENO, candidate, on_path=False)
    return None


def has_module(
    name: str, *, find_spec: Callable[[str], object | None] = importlib.util.find_spec
) -> bool:
    """Whether module ``name`` is importable, without importing it."""
    try:
        return find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def has_ejs_scripts(
    *, find_spec: Callable[[str], object | None] = importlib.util.find_spec
) -> bool:
    """Whether yt-dlp's challenge-solver scripts (``yt-dlp-ejs``) are installed."""
    return has_module(EJS_MODULE, find_spec=find_spec)


def check_requirements(
    *,
    warn: bool = True,
    which: Callable[[str], str | None] = shutil.which,
    search_dirs: Iterable[Path] | None = None,
    find_spec: Callable[[str], object | None] = importlib.util.find_spec,
) -> list[str]:
    """Check what YouTube downloads need, and say how to fix what's missing.

    Never raises. Each problem is a message ending with the fix.

    Args:
        warn: Also emit each problem as a :class:`DownloadRequirementWarning`.
        which, search_dirs: See :func:`find_js_runtime`.
        find_spec: Module lookup for :func:`has_module`.

    Returns:
        The problems found; empty when downloads should work.
    """
    problems = []
    if not has_module(YT_DLP_MODULE, find_spec=find_spec):
        problems.append(
            "yt-dlp is not installed. Install it with its default extras: "
            "pip install 'yb[download]' (or pip install 'yt-dlp[default]')."
        )
    elif not has_ejs_scripts(find_spec=find_spec):
        problems.append(
            "yt-dlp's JavaScript challenge-solver scripts (yt-dlp-ejs) are not "
            "installed, so YouTube downloads will fail with 'No video formats "
            "found'. Install yt-dlp with its default extras: "
            "pip install 'yt-dlp[default]' (or pip install 'yb[download]'). "
            f"See {EJS_WIKI_URL}"
        )
    runtime = find_js_runtime(which=which, search_dirs=search_dirs)
    if runtime is None:
        problems.append(
            "No JavaScript runtime found: YouTube downloads need Deno to solve "
            "YouTube's challenge, else they fail with 'No video formats found'. "
            f"Install it with: {DENO_INSTALL_CMD} "
            "then add ~/.deno/bin to PATH (e.g. in ~/.profile: "
            'export PATH="$HOME/.deno/bin:$PATH"). '
            f"See {EJS_WIKI_URL}"
        )
    if warn:
        for p in problems:
            warnings.warn(p, DownloadRequirementWarning, stacklevel=2)
    return problems


def yt_dlp_runtime_opts(
    runtime: JsRuntime | None,
) -> dict[str, dict[str, dict[str, str]]]:
    """yt-dlp options pointing at ``runtime`` when yt-dlp can't find it alone.

    Empty when there's nothing to add (no runtime, or it's already on ``PATH``).
    """
    if runtime is None or runtime.on_path:
        return {}
    return {JS_RUNTIMES_OPT: {runtime.name: {"path": str(runtime.path)}}}


@lru_cache(maxsize=1)
def _preflight_opts() -> tuple[tuple[str, object], ...]:
    """Check once per process: warn about gaps, return opts that close one."""
    check_requirements(warn=True)
    return tuple(yt_dlp_runtime_opts(find_js_runtime()).items())


def with_runtime_opts(opts: dict) -> dict:
    """``opts`` plus the preflight's runtime path, unless ``opts`` names runtimes.

    The first call per process runs :func:`check_requirements` (warning, never
    raising). An explicit ``js_runtimes`` in ``opts`` always wins.
    """
    extra = dict(_preflight_opts())
    if JS_RUNTIMES_OPT in opts:
        return opts
    return {**extra, **opts}

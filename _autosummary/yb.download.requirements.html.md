# yb.download.requirements

Preflight for downloading: does yt-dlp have what YouTube now demands?

YouTube makes yt-dlp solve a JavaScript “n challenge”. Without a solver it
fails late and cryptically (`No video formats found!`). Solving needs two
things:

- yt-dlp’s challenge-solver scripts, shipped by `yt-dlp[default]` (the
  `yt-dlp-ejs` package), which `yb[download]` depends on;
- a JavaScript runtime. **Deno** is the one yt-dlp enables by default, and the
  one that works.

Deno’s installer puts it in `~/.deno/bin` and only adds that to `PATH` for
interactive shells, so a cron job or service often can’t see it. This module
also looks there, and [`yt_dlp_runtime_opts()`](#yb.download.requirements.yt_dlp_runtime_opts) hands yt-dlp the explicit
path, so downloads work without touching `PATH`.

```pycon
>>> from yb.download import check_requirements
>>> problems = check_requirements()
>>> print("\n\n".join(problems) or "ready")
```

Nothing here raises: missing pieces are reported (and, by default, warned) with
the command that fixes them.

### Module Attributes

| [`DENO`](#yb.download.requirements.DENO)                      | The JavaScript runtime yt-dlp enables by default, and the one that works.                           |
|----------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------|
| [`DENO_INSTALL_CMD`](#yb.download.requirements.DENO_INSTALL_CMD)          | Deno's official installer.                                                                          |
| [`DENO_INSTALL_ENV`](#yb.download.requirements.DENO_INSTALL_ENV)          | Env var Deno's installer honours for its install root (binary in `<root>/bin`).                     |
| [`YT_DLP_MODULE`](#yb.download.requirements.YT_DLP_MODULE)             | yt-dlp's import name.                                                                               |
| [`EJS_MODULE`](#yb.download.requirements.EJS_MODULE)                | Module that carries yt-dlp's challenge-solver scripts (from `yt-dlp[default]`).                     |
| [`DENO_UPGRADE_CMD`](#yb.download.requirements.DENO_UPGRADE_CMD)          | Command that brings an installed Deno up to date.                                                   |
| [`DENO_MIN_VERSION_FALLBACK`](#yb.download.requirements.DENO_MIN_VERSION_FALLBACK) | Fallback for Deno's minimum version when yt-dlp can't be asked (not importable, or too old to say). |
| [`DENO_VERSION_TIMEOUT`](#yb.download.requirements.DENO_VERSION_TIMEOUT)      | Seconds to wait for `deno --version`.                                                               |
| [`EJS_WIKI_URL`](#yb.download.requirements.EJS_WIKI_URL)              | yt-dlp's notes on the JavaScript challenge.                                                         |
| [`JS_RUNTIMES_OPT`](#yb.download.requirements.JS_RUNTIMES_OPT)           | The yt-dlp option naming JS runtimes (`{"deno": {"path": ...}}`).                                   |

### Functions

| [`check_requirements`](#yb.download.requirements.check_requirements)(\*[, warn, which, ...])   | Check what YouTube downloads need, and say how to fix what's missing.   |
|-----------------------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`deno_search_dirs`](#yb.download.requirements.deno_search_dirs)()                           | Where Deno lives when it isn't on `PATH`.                               |
| [`deno_version`](#yb.download.requirements.deno_version)(runtime, \*[, run])             | Ask `runtime` for its version (`deno --version`); `None` if unknown.    |
| [`find_js_runtime`](#yb.download.requirements.find_js_runtime)(\*[, which, search_dirs])    | Find Deno on `PATH`, else in its standard install location.             |
| [`has_ejs_scripts`](#yb.download.requirements.has_ejs_scripts)(\*[, find_spec])             | Whether yt-dlp's challenge-solver scripts (`yt-dlp-ejs`) are installed. |
| [`has_module`](#yb.download.requirements.has_module)(name, \*[, find_spec])            | Whether module `name` is importable, without importing it.              |
| [`min_deno_version`](#yb.download.requirements.min_deno_version)(\*[, import_module])        | The oldest Deno yt-dlp supports, as a version tuple.                    |
| [`with_runtime_opts`](#yb.download.requirements.with_runtime_opts)(opts)                      | `opts` plus the preflight's runtime path, unless `opts` names runtimes. |
| [`yt_dlp_runtime_opts`](#yb.download.requirements.yt_dlp_runtime_opts)(runtime)                 | yt-dlp options pointing at `runtime` when yt-dlp can't find it alone.   |

### Classes

| [`JsRuntime`](#yb.download.requirements.JsRuntime)(name, path, on_path)   | A JavaScript runtime found for yt-dlp.   |
|-----------------------------------------------------------------------------------|------------------------------------------|

### Exceptions

| [`DownloadRequirementWarning`](#yb.download.requirements.DownloadRequirementWarning)   | A download prerequisite (JS runtime, solver scripts) looks missing.   |
|-------------------------------------------------------------------------------|-----------------------------------------------------------------------|

### yb.download.requirements.DENO *= 'deno'*

The JavaScript runtime yt-dlp enables by default, and the one that works.

### yb.download.requirements.DENO_INSTALL_CMD *= 'curl -fsSL https://deno.land/install.sh | sh'*

Deno’s official installer.

### yb.download.requirements.DENO_INSTALL_ENV *= 'DENO_INSTALL'*

Env var Deno’s installer honours for its install root (binary in `<root>/bin`).

### yb.download.requirements.DENO_MIN_VERSION_FALLBACK *= (2, 3, 0)*

Fallback for Deno’s minimum version when yt-dlp can’t be asked (not
importable, or too old to say). yt-dlp’s own value wins: see
[`min_deno_version()`](#yb.download.requirements.min_deno_version).

### yb.download.requirements.DENO_UPGRADE_CMD *= 'deno upgrade'*

Command that brings an installed Deno up to date.

### yb.download.requirements.DENO_VERSION_TIMEOUT *= 10*

Seconds to wait for `deno --version`.

### *exception* yb.download.requirements.DownloadRequirementWarning

Bases: [`UserWarning`](https://docs.python.org/3/builtins/exceptions.html#UserWarning)

A download prerequisite (JS runtime, solver scripts) looks missing.

### yb.download.requirements.EJS_MODULE *= 'yt_dlp_ejs'*

Module that carries yt-dlp’s challenge-solver scripts (from `yt-dlp[default]`).

### yb.download.requirements.EJS_WIKI_URL *= 'https://github.com/yt-dlp/yt-dlp/wiki/EJS'*

yt-dlp’s notes on the JavaScript challenge.

### yb.download.requirements.JS_RUNTIMES_OPT *= 'js_runtimes'*

The yt-dlp option naming JS runtimes (`{"deno": {"path": ...}}`).

### *class* yb.download.requirements.JsRuntime(name, path, on_path)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A JavaScript runtime found for yt-dlp.

#### name

yt-dlp’s key for the runtime (e.g. `"deno"`).

* **Type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

#### path

The executable.

* **Type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

#### on_path

Whether yt-dlp would find it by name on `PATH` unaided.

* **Type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### yb.download.requirements.YT_DLP_MODULE *= 'yt_dlp'*

yt-dlp’s import name.

### yb.download.requirements.check_requirements(\*, warn=True, which=<function which>, search_dirs=None, find_spec=<function find_spec>, run=<function run>, import_module=<function import_module>, check_deno_version=True)

Check what YouTube downloads need, and say how to fix what’s missing.

Never raises. Each problem is a message ending with the fix.

* **Parameters:**
  * **warn** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Also emit each problem as a [`DownloadRequirementWarning`](#yb.download.requirements.DownloadRequirementWarning).
  * **which** ([`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)]) – See [`find_js_runtime()`](#yb.download.requirements.find_js_runtime).
  * **search_dirs** ([`Iterable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterable)[[`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – See [`find_js_runtime()`](#yb.download.requirements.find_js_runtime).
  * **find_spec** ([`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`object`](https://docs.python.org/3/builtins/functions.html#object) | [`None`](https://docs.python.org/3/builtins/constants.html#None)]) – Module lookup for [`has_module()`](#yb.download.requirements.has_module).
  * **run** ([`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis), [`CompletedProcess`](https://docs.python.org/3/library/subprocess.html#subprocess.CompletedProcess)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]) – Subprocess runner for [`deno_version()`](#yb.download.requirements.deno_version).
  * **import_module** ([`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`object`](https://docs.python.org/3/builtins/functions.html#object)]) – Importer for [`min_deno_version()`](#yb.download.requirements.min_deno_version).
  * **check_deno_version** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Also run `deno --version` and compare it with
    yt-dlp’s minimum. The download preflight turns this off: it spawns
    a process, which belongs in an explicit check, not in a download.
* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
* **Returns:**
  The problems found; empty when downloads should work.

### yb.download.requirements.deno_search_dirs()

Where Deno lives when it isn’t on `PATH`.

This Python’s scripts dir and its interpreter’s dir (a pip-installed Deno,
e.g. `yt-dlp[deno]`, in a venv that isn’t activated: yt-dlp looks there
too), then the installer’s `$DENO_INSTALL/bin` and `~/.deno/bin`.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

### yb.download.requirements.deno_version(runtime, \*, run=<function run>)

Ask `runtime` for its version (`deno --version`); `None` if unknown.

Never raises: a runtime that can’t be run, or prints something unexpected,
has an unknown version (which [`check_requirements()`](#yb.download.requirements.check_requirements) doesn’t flag).

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`int`](https://docs.python.org/3/builtins/functions.html#int), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### yb.download.requirements.find_js_runtime(\*, which=<function which>, search_dirs=None)

Find Deno on `PATH`, else in its standard install location.

* **Parameters:**
  * **which** ([`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)]) – `PATH` lookup (injectable for tests).
  * **search_dirs** ([`Iterable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterable)[[`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Extra directories to look in when it isn’t on `PATH`
    (default [`deno_search_dirs()`](#yb.download.requirements.deno_search_dirs)).
* **Return type:**
  [`JsRuntime`](#yb.download.requirements.JsRuntime) | [`None`](https://docs.python.org/3/builtins/constants.html#None)
* **Returns:**
  The runtime found, or `None`.

### yb.download.requirements.has_ejs_scripts(\*, find_spec=<function find_spec>)

Whether yt-dlp’s challenge-solver scripts (`yt-dlp-ejs`) are installed.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### yb.download.requirements.has_module(name, \*, find_spec=<function find_spec>)

Whether module `name` is importable, without importing it.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### yb.download.requirements.min_deno_version(\*, import_module=<function import_module>)

The oldest Deno yt-dlp supports, as a version tuple.

Read from yt-dlp (`DenoJsRuntime.MIN_SUPPORTED_VERSION`) so it follows
yt-dlp’s upgrades; [`DENO_MIN_VERSION_FALLBACK`](#yb.download.requirements.DENO_MIN_VERSION_FALLBACK) when yt-dlp isn’t
importable or doesn’t say.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`int`](https://docs.python.org/3/builtins/functions.html#int), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

### yb.download.requirements.with_runtime_opts(opts)

`opts` plus the preflight’s runtime path, unless `opts` names runtimes.

The first call per process runs [`check_requirements()`](#yb.download.requirements.check_requirements) (warning, never
raising). An explicit `js_runtimes` in `opts` always wins, and skips the
check: the caller has chosen a runtime.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### yb.download.requirements.yt_dlp_runtime_opts(runtime)

yt-dlp options pointing at `runtime` when yt-dlp can’t find it alone.

Empty when there’s nothing to add (no runtime, or it’s already on `PATH`).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]]

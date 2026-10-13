"""The download preflight: find Deno (on PATH or in ~/.deno/bin), report gaps.

No network and no real runtime: PATH lookup, module lookup and yt-dlp itself
are all faked.
"""

import sys
import types
import warnings

import pytest

from yb.__main__ import main
from yb.download import requirements as req
from yb.download import youtube as ytdl


def _no_which(name):
    return None


def _found_spec(name):
    return object()


def _missing_spec(name):
    return None


def _fake_deno(directory):
    deno = directory / "deno"
    deno.write_text("#!/bin/sh\n")
    deno.chmod(0o755)
    return deno


@pytest.fixture(autouse=True)
def _fresh_preflight():
    req._preflight_opts.cache_clear()
    yield
    req._preflight_opts.cache_clear()


def test_deno_on_path_is_used_as_is():
    rt = req.find_js_runtime(which=lambda n: "/usr/bin/deno", search_dirs=[])
    assert rt is not None and rt.on_path
    assert req.yt_dlp_runtime_opts(rt) == {}


def test_deno_off_path_is_found_in_its_install_dir(tmp_path):
    deno = _fake_deno(tmp_path)
    rt = req.find_js_runtime(which=_no_which, search_dirs=[tmp_path])
    assert rt == req.JsRuntime("deno", deno, on_path=False)
    assert req.yt_dlp_runtime_opts(rt) == {"js_runtimes": {"deno": {"path": str(deno)}}}


def test_non_executable_file_is_not_a_runtime(tmp_path):
    (tmp_path / "deno").write_text("")
    assert req.find_js_runtime(which=_no_which, search_dirs=[tmp_path]) is None


def test_default_search_dirs_honour_deno_install(tmp_path, monkeypatch):
    monkeypatch.setenv("DENO_INSTALL", str(tmp_path))
    dirs = req.deno_search_dirs()
    assert dirs[0] == tmp_path / "bin"
    assert dirs[-1].parts[-2:] == (".deno", "bin")


def test_missing_runtime_is_reported_with_the_install_command(tmp_path):
    problems = req.check_requirements(
        warn=False, which=_no_which, search_dirs=[tmp_path], find_spec=_found_spec
    )
    assert len(problems) == 1
    assert req.DENO_INSTALL_CMD in problems[0]
    assert ".deno/bin" in problems[0] and "PATH" in problems[0]


def test_missing_solver_scripts_point_at_the_default_extra(tmp_path):
    _fake_deno(tmp_path)
    problems = req.check_requirements(
        warn=False,
        which=_no_which,
        search_dirs=[tmp_path],
        find_spec=lambda name: None if name == req.EJS_MODULE else object(),
    )
    assert len(problems) == 1 and "yt-dlp[default]" in problems[0]
    assert "yt-dlp-ejs" in problems[0]


def test_missing_yt_dlp_is_one_problem_not_two(tmp_path):
    _fake_deno(tmp_path)
    problems = req.check_requirements(
        warn=False, which=_no_which, search_dirs=[tmp_path], find_spec=_missing_spec
    )
    assert len(problems) == 1 and "yt-dlp is not installed" in problems[0]


def test_all_present_means_no_problems_and_no_warnings(tmp_path):
    _fake_deno(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert (
            req.check_requirements(
                which=_no_which, search_dirs=[tmp_path], find_spec=_found_spec
            )
            == []
        )


def test_problems_warn_and_never_raise(tmp_path):
    with pytest.warns(req.DownloadRequirementWarning):
        problems = req.check_requirements(
            which=_no_which, search_dirs=[tmp_path], find_spec=_missing_spec
        )
    assert len(problems) == 2


def test_broken_module_lookup_counts_as_missing():
    def _raises(name):
        raise ValueError("bad spec")

    assert req.has_ejs_scripts(find_spec=_raises) is False


def test_explicit_js_runtimes_always_win(monkeypatch, tmp_path):
    deno = _fake_deno(tmp_path)
    monkeypatch.setattr(req, "check_requirements", lambda **k: [])
    monkeypatch.setattr(
        req, "find_js_runtime", lambda: req.JsRuntime("deno", deno, on_path=False)
    )
    mine = {"js_runtimes": {"node": {}}, "quiet": True}
    assert req.with_runtime_opts(mine) == mine
    assert req.with_runtime_opts({"quiet": True}) == {
        "js_runtimes": {"deno": {"path": str(deno)}},
        "quiet": True,
    }


class _FakeYDL:
    seen: list = []

    def __init__(self, opts):
        type(self).seen.append(opts)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        return {"id": "abc", "title": "T"}


def test_downloads_hand_yt_dlp_the_off_path_runtime(monkeypatch, tmp_path):
    deno = _fake_deno(tmp_path)
    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=_FakeYDL))
    monkeypatch.setattr(req, "check_requirements", lambda **k: [])
    monkeypatch.setattr(
        req, "find_js_runtime", lambda: req.JsRuntime("deno", deno, on_path=False)
    )
    _FakeYDL.seen = []
    assert ytdl.youtube_video_info("https://youtu.be/abc")["id"] == "abc"
    assert _FakeYDL.seen[-1]["js_runtimes"] == {"deno": {"path": str(deno)}}
    ytdl.youtube_video_info("u", extra_opts={"js_runtimes": {"node": {}}})
    assert _FakeYDL.seen[-1]["js_runtimes"] == {"node": {}}


def test_preflight_runs_once_per_process(monkeypatch):
    calls = []
    monkeypatch.setattr(req, "check_requirements", lambda **k: calls.append(k) or [])
    monkeypatch.setattr(req, "find_js_runtime", lambda: None)
    req.with_runtime_opts({})
    req.with_runtime_opts({})
    assert len(calls) == 1


def test_yb_check_exit_status(monkeypatch, capsys):
    monkeypatch.setattr(req, "find_js_runtime", lambda **k: None)
    monkeypatch.setattr(req, "check_requirements", lambda **k: ["no deno: install it"])
    assert main(["check"]) == 1
    assert "install it" in capsys.readouterr().err
    monkeypatch.setattr(req, "check_requirements", lambda **k: [])
    assert main(["check"]) == 0
    assert "ready" in capsys.readouterr().out

"""``check_cookies`` and ``yb check --online``: the metadata fetch is faked."""

import pytest

from yb.__main__ import main
from yb.download import probe
from yb.download import requirements as req
from yb.download.probe import COOKIE_EXPORT_STEPS, PROBE_VIDEO_URL, check_cookies


def fetcher(*, warn=None, error=None, seen=None):
    def fetch(url, *, cookies_file, extra_opts):
        if seen is not None:
            seen.append((url, cookies_file))
        if warn:
            extra_opts["logger"].warning(warn)
        if error:
            raise error
        return {"id": "jNQXAC9IVRw"}

    return fetch


@pytest.fixture
def jar(tmp_path):
    path = tmp_path / "cookies.txt"
    path.write_text("# Netscape HTTP Cookie File\n")
    return path


def test_working_cookies_have_no_problem(jar):
    seen = []
    assert check_cookies(jar, fetch_info=fetcher(seen=seen)) == []
    assert seen == [(PROBE_VIDEO_URL, jar)]


def test_rotated_cookies_say_so_with_the_export_steps(jar):
    warn = "[youtube] The provided YouTube account cookies are no longer valid. ..."
    (msg,) = check_cookies(jar, fetch_info=fetcher(warn=warn))
    assert "rotated or expired" in msg and str(jar) in msg
    assert msg.endswith(COOKIE_EXPORT_STEPS)


def test_bot_wall_says_the_cookies_were_refused(jar):
    error = Exception("ERROR: [youtube] x: Sign in to confirm you're not a bot.")
    (msg,) = check_cookies(jar, fetch_info=fetcher(error=error))
    assert "bot check refused" in msg and COOKIE_EXPORT_STEPS in msg


def test_other_failures_are_reported_not_raised(jar):
    (msg,) = check_cookies(jar, fetch_info=fetcher(error=OSError("no network")))
    assert "no network" in msg


def test_unrelated_warnings_are_not_problems(jar):
    assert check_cookies(jar, fetch_info=fetcher(warn="[youtube] slow")) == []


def test_no_cookies_file_means_nothing_to_check(monkeypatch):
    monkeypatch.setattr(probe, "default_cookies_file", lambda: None)
    seen = []
    assert check_cookies(fetch_info=fetcher(seen=seen)) == []
    assert check_cookies(False, fetch_info=fetcher(seen=seen)) == []
    assert seen == []


def test_default_cookies_file_is_the_one_probed(monkeypatch, jar):
    monkeypatch.setattr(probe, "default_cookies_file", lambda: jar)
    seen = []
    check_cookies(fetch_info=fetcher(seen=seen))
    assert seen == [(PROBE_VIDEO_URL, jar)]


@pytest.fixture
def ready(monkeypatch):
    monkeypatch.setattr(req, "find_js_runtime", lambda **k: None)
    monkeypatch.setattr(req, "check_requirements", lambda **k: [])
    monkeypatch.setattr(req, "has_module", lambda name, **k: True)


def test_yb_check_online_reports_cookie_problems(ready, monkeypatch, capsys):
    monkeypatch.setattr(probe, "check_cookies", lambda: ["cookies rotated: re-export"])
    assert main(["check", "--online"]) == 1
    assert "re-export" in capsys.readouterr().err
    assert main(["check"]) == 0  # offline: no probe


def test_yb_check_names_the_po_token_provider(ready, monkeypatch, capsys):
    monkeypatch.setattr(req, "installed_version", lambda dist: None)
    main(["check"])
    assert "pip install 'yb[pot]'" in capsys.readouterr().out
    monkeypatch.setattr(req, "installed_version", lambda dist: "2.0.2")
    main(["check"])
    assert f"{req.PO_TOKEN_PROVIDER_DIST} 2.0.2" in capsys.readouterr().out


def test_installed_version():
    assert req.installed_version("pytest")
    assert req.installed_version("surely-not-a-distribution-xyz") is None

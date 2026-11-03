"""``check_cookies`` and ``yb check --online``: the metadata fetch is faked."""

import importlib.metadata
from pathlib import Path

import pytest

from yb.__main__ import main
from yb.download import probe
from yb.download import requirements as req
from yb.download.probe import (
    COOKIE_EXPORT_STEPS,
    PROBE_VIDEO_URL,
    check_cookies,
    check_po_token_server,
)


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


LOGGED_IN = (
    "# Netscape HTTP Cookie File\n"
    ".youtube.com\tTRUE\t/\tTRUE\t4102444800\tLOGIN_INFO\tx\n"
    "#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t4102444800\t__Secure-3PAPISID\ty\n"
)


@pytest.fixture
def jar(tmp_path, monkeypatch):
    monkeypatch.delenv("YB_COOKIES_FILE", raising=False)
    path = tmp_path / "cookies.txt"
    path.write_text(LOGGED_IN)
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


def test_bot_wall_says_the_cookies_or_the_ip_were_refused(jar):
    error = Exception("ERROR: [youtube] x: Sign in to confirm you're not a bot.")
    (msg,) = check_cookies(jar, fetch_info=fetcher(error=error))
    assert "bot check refused" in msg and "this IP" in msg
    assert COOKIE_EXPORT_STEPS in msg


@pytest.mark.parametrize(
    "content",
    [
        "# Netscape HTTP Cookie File\n",  # empty
        "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t4102444800\tLOGIN_INFO\tx\n",
        # expired session id
        LOGGED_IN.replace("4102444800\t__Secure", "1000000000\t__Secure"),
        # someone else's domain
        LOGGED_IN.replace(".youtube.com", ".example.com"),
    ],
)
def test_a_jar_without_a_logged_in_session_is_a_problem_before_any_request(
    jar, content
):
    jar.write_text(content)
    seen = []
    (msg,) = check_cookies(jar, fetch_info=fetcher(seen=seen))
    assert "no logged-in YouTube session" in msg and COOKIE_EXPORT_STEPS in msg
    assert seen == []


def test_an_unreadable_jar_is_a_problem(jar):
    jar.write_text("not a cookies file\n")
    (msg,) = check_cookies(jar, fetch_info=fetcher())
    assert "Netscape" in msg


def test_a_named_env_file_that_is_missing_is_a_problem(monkeypatch, tmp_path):
    monkeypatch.setenv("YB_COOKIES_FILE", str(tmp_path / "typo.txt"))
    (msg,) = check_cookies(fetch_info=fetcher())
    assert "typo.txt" in msg and "does not exist" in msg


def test_an_explicit_missing_file_is_a_problem(tmp_path):
    (msg,) = check_cookies(tmp_path / "nope.txt", fetch_info=fetcher())
    assert "not found" in msg


def test_the_default_probe_never_rewrites_the_file(jar, monkeypatch):
    """yt-dlp saves its jar on exit; the probe must hand it a copy."""
    from yb.download import youtube as ytdl

    given = {}

    class FakeYDL:
        def __init__(self, opts):
            given.update(opts)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            Path(given["cookiefile"]).write_text("# rewritten by yt-dlp\n")

        def extract_info(self, url, download):
            return {"id": "x"}

    monkeypatch.setattr(ytdl, "youtube_dl_cls", lambda: FakeYDL)
    monkeypatch.setattr(ytdl, "with_runtime_opts", lambda o: o)
    before = jar.read_bytes()
    assert check_cookies(jar) == []
    assert given["cookiefile"] != str(jar) and jar.read_bytes() == before


def test_other_failures_are_reported_not_raised(jar):
    (msg,) = check_cookies(jar, fetch_info=fetcher(error=OSError("no network")))
    assert "no network" in msg


def test_unrelated_warnings_are_not_problems(jar):
    assert check_cookies(jar, fetch_info=fetcher(warn="[youtube] slow")) == []


def test_no_cookies_file_means_nothing_to_check(monkeypatch):
    monkeypatch.delenv("YB_COOKIES_FILE", raising=False)
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


def test_po_token_server_ping():
    urls = []

    class Ok:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def up(url, timeout):
        urls.append((url, timeout))
        return Ok()

    def down(url, timeout):
        raise OSError("connection refused")

    assert check_po_token_server("http://127.0.0.1:4416/", urlopen=up) == []
    assert urls == [("http://127.0.0.1:4416/ping", probe.PING_TIMEOUT_S)]
    (msg,) = check_po_token_server(urlopen=down)
    assert "connection refused" in msg and "127.0.0.1:4416:4416" in msg


@pytest.fixture
def ready(monkeypatch):
    monkeypatch.setattr(req, "find_js_runtime", lambda **k: None)
    monkeypatch.setattr(req, "check_requirements", lambda **k: [])
    monkeypatch.setattr(req, "has_module", lambda name, **k: True)


def test_yb_check_online_reports_cookie_problems(ready, monkeypatch, capsys):
    monkeypatch.setattr(req, "installed_version", lambda dist: None)
    monkeypatch.setattr(probe, "check_cookies", lambda: ["cookies rotated: re-export"])
    assert main(["check", "--online"]) == 1
    assert "re-export" in capsys.readouterr().err
    assert main(["check"]) == 0  # offline: no probe


def test_yb_check_online_says_what_it_probed(ready, monkeypatch, capsys, jar):
    monkeypatch.setattr(req, "installed_version", lambda dist: None)
    monkeypatch.setattr(probe, "check_cookies", lambda: [])
    monkeypatch.setattr(probe, "configured_cookies", lambda: (None, None))
    assert main(["check", "--online"]) == 0
    assert "none configured" in capsys.readouterr().out
    monkeypatch.setattr(probe, "configured_cookies", lambda: (jar, None))
    main(["check", "--online"])
    assert "logged-in session YouTube accepts" in capsys.readouterr().out


def test_yb_check_online_pings_an_installed_provider(ready, monkeypatch, capsys):
    monkeypatch.setattr(req, "installed_version", lambda dist: "2.0.2")
    monkeypatch.setattr(probe, "check_cookies", lambda: [])
    monkeypatch.setattr(probe, "check_po_token_server", lambda: ["server down"])
    assert main(["check", "--online"]) == 1
    assert "server down" in capsys.readouterr().err


def test_yb_check_names_the_po_token_provider(ready, monkeypatch, capsys):
    monkeypatch.setattr(req, "installed_version", lambda dist: None)
    main(["check"])
    assert "--online says more" in capsys.readouterr().out
    monkeypatch.setattr(probe, "check_cookies", lambda: [])
    main(["check", "--online"])
    assert "pip install 'yb[pot]'" in capsys.readouterr().out
    monkeypatch.setattr(req, "installed_version", lambda dist: "2.0.2")
    main(["check"])
    assert f"{req.PO_TOKEN_PROVIDER_DIST} 2.0.2" in capsys.readouterr().out


def test_installed_version():
    def version(dist):
        if dist == "there":
            return "1.0"
        raise importlib.metadata.PackageNotFoundError(dist)

    assert req.installed_version("there", version=version) == "1.0"
    assert req.installed_version("missing", version=version) is None

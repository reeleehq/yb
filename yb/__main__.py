"""Command line for ``yb``: ``python -m yb`` / the ``yb`` script.

``auth``: YouTube consent that works from a machine with no browser and no
terminal (a session driven from a phone), by pasting the browser's redirect
back::

    yb auth                          # print the consent URL
    yb auth --paste '<redirected URL>'   # finish; also - (stdin) or @file
    yb auth --check                  # is a usable token cached? (never prompts)
    yb auth --profile reelee         # same, for the named account/channel

``whoami``: which channel does a profile's token upload to? (run before
publishing; never uploads)::

    yb whoami --profile reelee

``check``: are YouTube downloads ready (JS runtime, solver scripts)? Prints what
is missing and how to install it; exit status 1 if anything is. ``--online``
also checks the cookies file holds a logged-in session and reads one public
video with it (one metadata fetch, on a copy of the file; catches rotated
cookies before a real download does), and pings the PO-token server::

    yb check
    yb check --online
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence


def _read_paste(value: str) -> str:
    """The pasted redirect: literally, from stdin (``-``), or from ``@file``.

    A file is only read when asked for with ``@``, so no pasted text can make
    this command open a file (a token, say) and send its contents to Google.
    """
    if value == "-":
        return sys.stdin.read()
    if value.startswith("@"):
        return Path(value[1:]).read_text()
    return value


def _auth(args: argparse.Namespace) -> int:
    from yb.youtube import ConsentPending, ConsentRequired, get_credentials

    kwargs = dict(
        client_secrets_file=args.client_secrets,
        token_file=args.token_file,
        profile=args.profile,
    )
    try:
        if args.check:
            get_credentials(interactive=False, **kwargs)
        else:
            get_credentials(
                consent="paste",
                port=args.port,
                authorization_response=_read_paste(args.paste) if args.paste else None,
                **kwargs,
            )
    except ConsentPending as pending:
        print(pending)
        return 0
    except ConsentRequired as error:
        print(error, file=sys.stderr)
        return 1
    print("YouTube credentials are valid and cached.")
    return 0


def _whoami(args: argparse.Namespace) -> int:
    from yb.config import load_config, resolve_profile
    from yb.youtube import ConsentRequired, WrongChannel, check_channel, get_service

    profile = resolve_profile(args.profile)
    label = profile or "default"
    try:
        cfg = load_config(profile=profile)
        service = get_service(profile=profile, interactive=False)
        channel = check_channel(service, cfg.channel_id)
    except (ConsentRequired, WrongChannel, KeyError) as error:
        print(error, file=sys.stderr)
        return 1
    expected = "matches config" if cfg.channel_id else "no channel_id in config"
    print(
        f"profile {label}: uploads to {channel['title']!r} "
        f"{channel['handle'] or ''} id={channel['id']} ({expected}); "
        f"privacy={cfg.privacy_status} playlist={cfg.playlist!r}"
    )
    return 0


def _check(args: argparse.Namespace) -> int:
    from yb.download import requirements as req

    problems = req.check_requirements(warn=False)
    notes = []
    if runtime := req.find_js_runtime():
        where = "on PATH" if runtime.on_path else "off PATH; yb passes yt-dlp its path"
        notes.append(f"JS runtime: {runtime.name} at {runtime.path} ({where})")
    pot = req.installed_version(req.PO_TOKEN_PROVIDER_DIST)
    if pot:
        notes.append(f"PO-token provider: {req.PO_TOKEN_PROVIDER_DIST} {pot}")
    elif args.online:
        notes.append(f"Note: {req.PO_TOKEN_HINT}")
    else:
        notes.append(
            "PO-token provider: none (needed only where YouTube answers the media "
            "with HTTP 403; yb check --online says more)"
        )
    if args.online and req.has_module(req.YT_DLP_MODULE):
        from yb.download import probe

        path, _ = probe.configured_cookies()
        cookie_problems = probe.check_cookies()
        problems += cookie_problems
        if path is None and not cookie_problems:
            notes.append("Cookies: none configured; nothing probed.")
        elif not cookie_problems:
            notes.append(f"Cookies: {path} is a logged-in session YouTube accepts.")
        if pot:
            problems += probe.check_po_token_server()
    for p in problems:
        print(f"- {p}", file=sys.stderr)
    for note in notes:
        print(note)
    if not problems:
        print("Downloads ready.")
    return 1 if problems else 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point; returns the process exit status."""
    parser = argparse.ArgumentParser(prog="yb", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    auth = commands.add_parser(
        "auth", help="YouTube consent by paste-back (no browser or terminal needed)"
    )
    mode = auth.add_mutually_exclusive_group()
    mode.add_argument(
        "--paste",
        metavar="URL",
        help="finish consent: the redirected URL (or its bare code); '-' reads "
        "stdin, '@path' reads a file",
    )
    mode.add_argument(
        "--check", action="store_true", help="only verify the cached token"
    )
    auth.add_argument(
        "--port", type=int, default=0, help="redirect port (default 8080)"
    )
    auth.add_argument("--client-secrets", help="OAuth client JSON (default: as usual)")
    auth.add_argument("--token-file", help="token cache location (default: as usual)")
    auth.add_argument(
        "--profile", help="named account (default: $YB_PROFILE, else the default)"
    )
    auth.set_defaults(run=_auth)
    whoami = commands.add_parser(
        "whoami", help="which channel does a profile's token upload to?"
    )
    whoami.add_argument(
        "--profile", help="named account (default: $YB_PROFILE, else the default)"
    )
    whoami.set_defaults(run=_whoami)
    check = commands.add_parser(
        "check", help="are YouTube downloads ready? (JS runtime, solver scripts)"
    )
    check.add_argument(
        "--online",
        action="store_true",
        help="also test the cookies file on a public video, and the PO-token server",
    )
    check.set_defaults(run=_check)
    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())

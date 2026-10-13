"""Command line for ``yb``: ``python -m yb`` / the ``yb`` script.

``auth``: YouTube consent that works from a machine with no browser and no
terminal (a session driven from a phone), by pasting the browser's redirect
back::

    yb auth                          # print the consent URL
    yb auth --paste '<redirected URL>'   # finish; also - (stdin) or @file
    yb auth --check                  # is a usable token cached? (never prompts)

``check``: are YouTube downloads ready (JS runtime, solver scripts)? Prints what
is missing and how to install it; exit status 1 if anything is::

    yb check
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

    kwargs = dict(client_secrets_file=args.client_secrets, token_file=args.token_file)
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


def _check(args: argparse.Namespace) -> int:
    from yb.download.requirements import check_requirements, find_js_runtime

    problems = check_requirements(warn=False)
    for p in problems:
        print(f"- {p}", file=sys.stderr)
    if runtime := find_js_runtime():
        where = "on PATH" if runtime.on_path else "off PATH; yb passes yt-dlp its path"
        print(f"JS runtime: {runtime.name} at {runtime.path} ({where})")
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
    auth.set_defaults(run=_auth)
    check = commands.add_parser(
        "check", help="are YouTube downloads ready? (JS runtime, solver scripts)"
    )
    check.set_defaults(run=_check)
    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())

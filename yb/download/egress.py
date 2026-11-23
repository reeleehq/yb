"""Connect-time address checks: the address a request connects to is the one checked.

A URL check (``validate_target``) resolves a host name, and the HTTP layer then
resolves it again to connect. Between the two, a name with a zero TTL can answer
a public address and then an internal one (DNS rebinding). And the HTTP layer
follows redirects itself, so a URL check sees where a chain ends, while every hop
before it has already been requested.

:func:`address_check` closes both at the one place every connection passes
through: name resolution. While it is active (in this thread or task), every
``socket.getaddrinfo`` answer is handed to a check before anything connects, so
the address checked is the address connected to, for the link, each redirect hop,
each manifest and each fragment alike.

    >>> import socket
    >>> def no_loopback(ip, port):
    ...     if ip.startswith("127."):
    ...         raise ValueError(f"refused {ip}")
    >>> with address_check(no_loopback):  # doctest: +SKIP
    ...     socket.getaddrinfo("localhost", 80)
    Traceback (most recent call last):
        ...
    ValueError: refused 127.0.0.1

Outside an active check, resolution is untouched. The patch is installed once,
on first use, and passes straight through when no check is active, so code in
other threads is unaffected. Work a library hands to a thread pool does not see
the check (a new thread starts with no context), so the caller must keep its
requests on the calling thread (yb pins ``concurrent_fragment_downloads`` to 1).
"""

from __future__ import annotations

import ipaddress
import socket
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

#: An address check: raises ``ValueError`` to refuse connecting to ``ip`` on ``port``.
AddressCheck = Callable[[str, "int | None"], None]

_active: ContextVar[AddressCheck | None] = ContextVar("yb_address_check", default=None)
_install_lock = threading.Lock()
_installed = False

#: The resolver the patch delegates to (the original ``socket.getaddrinfo``).
#: A module attribute, looked up on every call, so tests can stand in a fake DNS.
_resolve = socket.getaddrinfo

_SERVICE_PORTS = {"http": 80, "https": 443}


def _port_number(port) -> int | None:
    """``getaddrinfo``'s port argument (int, digits, a service name or None) as a number."""
    if port is None or isinstance(port, int):
        return port
    if isinstance(port, bytes):
        port = port.decode()
    if str(port).isdigit():
        return int(port)
    return _SERVICE_PORTS.get(str(port).lower())


def _checked_getaddrinfo(host, port, *args, **kwargs):
    infos = _resolve(host, port, *args, **kwargs)
    check = _active.get()
    if check is not None:
        number = _port_number(port)
        for info in infos:
            check(info[4][0], number)
    return infos


def _install() -> None:
    global _installed
    with _install_lock:
        if not _installed:
            socket.getaddrinfo = _checked_getaddrinfo
            _installed = True


@contextmanager
def address_check(check: AddressCheck) -> Iterator[None]:
    """Run ``check(ip, port)`` on every address resolved in this context, before any connect.

    Every address a name resolves to is checked, not only the first: a name with
    one public and one internal record is refused, since the connection may use
    either. ``check`` raises (a ``ValueError``) to refuse; the error propagates out
    of the resolution, so nothing connects.
    """
    _install()
    token = _active.set(check)
    try:
        yield
    finally:
        _active.reset(token)


def url_of_address(ip: str, port: int | None) -> str:
    """An ``http`` URL whose host is the address itself, for a URL-level target check.

    It lets a URL check (one that resolves names and refuses internal addresses)
    judge an address with no second lookup: an IP literal resolves to itself.

    >>> url_of_address("10.0.0.1", 443), url_of_address("::1", 80), url_of_address("1.2.3.4", None)
    ('http://10.0.0.1:443/', 'http://[::1]:80/', 'http://1.2.3.4/')
    """
    bare = ip.split("%", 1)[0]  # an IPv6 zone index is not part of a URL host
    host = f"[{bare}]" if ipaddress.ip_address(bare).version == 6 else bare
    return f"http://{host}:{port}/" if port else f"http://{host}/"

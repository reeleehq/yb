# yb.download.egress

Connect-time address checks: the address a request connects to is the one checked.

A URL check (`validate_target`) resolves a host name, and the HTTP layer then
resolves it again to connect. Between the two, a name with a zero TTL can answer
a public address and then an internal one (DNS rebinding). And the HTTP layer
follows redirects itself, so a URL check sees where a chain ends, while every hop
before it has already been requested.

[`address_check()`](#yb.download.egress.address_check) closes both at the one place every connection passes
through: name resolution. While it is active (in this thread or task), every
`socket.getaddrinfo` answer is handed to a check before anything connects, so
the address checked is the address connected to, for the link, each redirect hop,
each manifest and each fragment alike.

```pycon
>>> import socket
>>> def no_loopback(ip, port):
...     if ip.startswith("127."):
...         raise ValueError(f"refused {ip}")
>>> with address_check(no_loopback):
...     socket.getaddrinfo("localhost", 80)
Traceback (most recent call last):
    ...
ValueError: refused 127.0.0.1
```

Outside an active check, resolution is untouched. The patch is (re)installed on
entry to each check, over whatever `socket.getaddrinfo` is then (another
library’s resolver keeps working underneath), and passes straight through when no
check is active, so code in other threads is unaffected. The check itself runs
with no check active, so a check that resolves names does not recurse. Work a library hands to a thread pool does not see
the check (a new thread starts with no context), so the caller must keep its
requests on the calling thread (yb pins `concurrent_fragment_downloads` to 1).

### Module Attributes

| [`AddressCheck`](#yb.download.egress.AddressCheck)   | raises `ValueError` to refuse connecting to `ip` on `port`.   |
|-----------------------------------------------------------------|---------------------------------------------------------------|

### Functions

| [`address_check`](#yb.download.egress.address_check)(check)     | Run `check(ip, port)` on every address resolved in this context, before any connect.                                |
|---------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------|
| [`no_address_check`](#yb.download.egress.no_address_check)()       | Suspend an active [`address_check()`](#yb.download.egress.address_check) (for a URL check's own lookups). |
| [`url_of_address`](#yb.download.egress.url_of_address)(ip, port) | An `http` URL whose host is the address itself, for a URL-level target check.                                       |

### yb.download.egress.AddressCheck

raises `ValueError` to refuse connecting to `ip` on `port`.

* **Type:**
  An address check

alias of [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), int | None], [`None`](https://docs.python.org/3/builtins/constants.html#None)]

### yb.download.egress.address_check(check)

Run `check(ip, port)` on every address resolved in this context, before any connect.

Every address a name resolves to is checked, not only the first: a name with
one public and one internal record is refused, since the connection may use
either. `check` raises (a `ValueError`) to refuse; the error propagates out
of the resolution, so nothing connects.

* **Return type:**
  [`Iterator`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterator)[[`None`](https://docs.python.org/3/builtins/constants.html#None)]

### yb.download.egress.no_address_check()

Suspend an active [`address_check()`](#yb.download.egress.address_check) (for a URL check’s own lookups).

* **Return type:**
  [`Iterator`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterator)[[`None`](https://docs.python.org/3/builtins/constants.html#None)]

### yb.download.egress.url_of_address(ip, port)

An `http` URL whose host is the address itself, for a URL-level target check.

It lets a URL check (one that resolves names and refuses internal addresses)
judge an address with no second lookup: an IP literal resolves to itself.

```pycon
>>> url_of_address("10.0.0.1", 443), url_of_address("::1", 80), url_of_address("1.2.3.4", None)
('http://10.0.0.1:443/', 'http://[::1]:80/', 'http://1.2.3.4/')
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

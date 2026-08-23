"""Fail-closed HTTP GET dla niezaufanych URL-i researchu V3.

Walidacja DNS bez przypięcia połączenia ma lukę TOCTOU. Ten adapter rozwiązuje
host raz, odrzuca cały mieszany zestaw, a backend httpcore łączy się wyłącznie
z zatwierdzonym literalnym IP. Oryginalny hostname pozostaje w żądaniu i SNI.
"""

from __future__ import annotations

import ipaddress
import json
import socket
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpcore
import httpx

import config


Resolver = Callable[[str, int], Iterable[str]]
TransportFactory = Callable[["ValidatedTarget"], httpx.BaseTransport]
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


class SafeFetchError(RuntimeError):
    """Bazowy błąd polityki lub transportu bezpiecznego fetchu."""


class UnsafeURL(SafeFetchError):
    """URL lub rozwiązany adres nie może opuścić procesu."""


class DNSResolutionError(SafeFetchError):
    """Host nie ma jednoznacznego publicznego rozwiązania DNS."""


class RedirectPolicyError(SafeFetchError):
    """Łańcuch przekierowań łamie politykę."""


class ResponseTooLarge(SafeFetchError):
    """Nieskompresowana odpowiedź przekroczyła limit typu treści."""


class FetchHTTPStatusError(SafeFetchError):
    """Odpowiedź końcowa ma status HTTP błędu."""


@dataclass(frozen=True)
class ValidatedTarget:
    url: str
    scheme: str
    hostname: str
    port: int
    ips: tuple[str, ...]


@dataclass(frozen=True)
class FetchHop:
    url: str
    hostname: str
    ips: tuple[str, ...]
    status_code: int


@dataclass(frozen=True)
class SafeResponse:
    status_code: int
    headers: Mapping[str, str]
    content: bytes
    url: str
    hops: tuple[FetchHop, ...]

    @property
    def text(self) -> str:
        content_type = self.headers.get("content-type", "")
        charset = "utf-8"
        for part in content_type.split(";")[1:]:
            key, separator, value = part.strip().partition("=")
            if separator and key.lower() == "charset" and value.strip():
                charset = value.strip().strip('"\'')
                break
        try:
            return self.content.decode(charset, errors="replace")
        except LookupError:
            return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.text)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise FetchHTTPStatusError(
                f"HTTP {self.status_code} dla {self.url}")

    @property
    def redirect_chain(self) -> tuple[str, ...]:
        return tuple(hop.url for hop in self.hops)

    @property
    def resolved_ips(self) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for hop in self.hops:
            # Ten sam host może wystąpić w kilku redirectach i zostać ponownie
            # rozwiązany. Nie wolno nadpisywać wcześniejszych pinów, bo baza
            # utraciłaby część pochodzenia mimo poprawnej walidacji transportu.
            known = result.setdefault(hop.hostname, [])
            for ip in hop.ips:
                if ip not in known:
                    known.append(ip)
        return result


def _ascii_host(hostname: str) -> str:
    try:
        return hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise UnsafeURL("nieprawidłowa nazwa IDNA") from exc


def _is_public_address(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> bool:
    """`is_global` sam dopuszcza multicast; research wymaga zwykłego unicastu."""
    return bool(
        address.is_global
        and not address.is_multicast
        and not address.is_private
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_reserved
        and not address.is_unspecified
    )


def normalize_url(url: str) -> str:
    """Kanonizuje składnię dokumentu bez wykonywania DNS."""
    raw = str(url or "").strip()
    if not raw or len(raw) > config.FETCH_MAX_URL_CHARS:
        raise UnsafeURL("pusty albo zbyt długi URL")
    if any(ord(character) < 32 for character in raw) or "\\" in raw:
        raise UnsafeURL("znaki kontrolne lub backslash w URL")
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise UnsafeURL("nieprawidłowy port lub składnia URL") from exc
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise UnsafeURL(f"niedozwolony schemat {scheme!r}")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeURL("userinfo w URL jest zabronione")
    if not parsed.hostname:
        raise UnsafeURL("URL nie ma hosta")
    hostname = _ascii_host(parsed.hostname)
    default_port = 443 if scheme == "https" else 80
    port = port or default_port
    if port != default_port:
        raise UnsafeURL(f"niestandardowy port {port} jest zabroniony")

    # Literal IP można ocenić bez DNS. Nazwa domenowa zostanie oceniona dopiero
    # przez `validate_url`, ale discovery może już bezpiecznie porównać ścieżkę.
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None and not _is_public_address(literal):
        raise UnsafeURL(f"niedozwolony adres {literal}")

    host_for_url = f"[{hostname}]" if ":" in hostname else hostname
    path = parsed.path or "/"
    return urlunsplit((scheme, host_for_url, path, parsed.query, ""))


def system_resolver(hostname: str, port: int) -> tuple[str, ...]:
    try:
        records = socket.getaddrinfo(
            hostname, port, family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP,
        )
    except socket.gaierror as exc:
        raise DNSResolutionError(
            f"DNS nie rozwiązał {hostname}: {exc}") from exc
    return tuple(str(record[4][0]) for record in records)


def validate_url(url: str, resolver: Resolver = system_resolver) -> ValidatedTarget:
    normalized = normalize_url(url)
    parsed = urlsplit(normalized)
    hostname = _ascii_host(parsed.hostname or "")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        literal = ipaddress.ip_address(hostname)
        raw_ips = (str(literal),)
    except ValueError:
        raw_ips = tuple(resolver(hostname, port))
    if not raw_ips:
        raise DNSResolutionError(f"DNS zwrócił pusty zestaw dla {hostname}")

    parsed_ips: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for raw_ip in raw_ips:
        try:
            address = ipaddress.ip_address(str(raw_ip).split("%", 1)[0])
        except ValueError as exc:
            raise DNSResolutionError(
                f"resolver zwrócił nieprawidłowy adres {raw_ip!r}") from exc
        if not _is_public_address(address):
            raise UnsafeURL(
                f"{hostname} rozwiązuje się do niedozwolonego {address}")
        parsed_ips.append(address)
    unique = tuple(str(item) for item in sorted(
        set(parsed_ips), key=lambda item: (item.version, int(item))))
    return ValidatedTarget(
        normalized, parsed.scheme, hostname, port, unique)


class PinnedDNSBackend(httpcore.SyncBackend):
    """Backend bez resolvera: host może połączyć się tylko z przypiętym IP."""

    def __init__(
        self, pins: Mapping[str, tuple[str, ...]],
        backend: httpcore.SyncBackend | None = None,
    ) -> None:
        self._pins = {_ascii_host(host): tuple(ips) for host, ips in pins.items()}
        self._backend = backend or httpcore.SyncBackend()

    def connect_tcp(
        self, host: str, port: int, timeout: float | None = None,
        local_address: str | None = None, socket_options=None,
    ):
        hostname = _ascii_host(host)
        ips = self._pins.get(hostname)
        if not ips:
            raise UnsafeURL(f"transport nie ma przypięcia dla {hostname}")
        last_error: Exception | None = None
        for ip in ips:
            try:
                return self._backend.connect_tcp(
                    ip, port, timeout=timeout, local_address=local_address,
                    socket_options=socket_options)
            except Exception as exc:  # kolejne zatwierdzone IP jest fallbackiem
                last_error = exc
        if last_error is not None:
            raise last_error
        raise DNSResolutionError(f"brak przypiętych IP dla {hostname}")

    def connect_unix_socket(self, *args, **kwargs):
        raise UnsafeURL("socket Unix jest zabroniony dla fetchu URL")

    def sleep(self, seconds: float) -> None:
        self._backend.sleep(seconds)


def pinned_transport(target: ValidatedTarget) -> httpx.HTTPTransport:
    """Buduje transport HTTPX z backendem przypiętym do zatwierdzonego DNS."""
    transport = httpx.HTTPTransport(
        verify=True, trust_env=False, http1=True, http2=False, retries=0,
        limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
    )
    old_pool = transport._pool  # httpx 0.28.1 jest przypięty w requirements
    ssl_context = getattr(old_pool, "_ssl_context", None)
    old_pool.close()
    transport._pool = httpcore.ConnectionPool(
        ssl_context=ssl_context, max_connections=1,
        max_keepalive_connections=0, http1=True, http2=False, retries=0,
        network_backend=PinnedDNSBackend({target.hostname: target.ips}),
    )
    return transport


def _limit_for(headers: Mapping[str, str], url: str) -> int:
    content_type = headers.get("content-type", "").lower()
    path = urlsplit(url).path.lower()
    if "pdf" in content_type or path.endswith(".pdf"):
        return config.FETCH_MAX_PDF_BYTES
    if "json" in content_type:
        return config.FETCH_MAX_JSON_BYTES
    return config.FETCH_MAX_HTML_BYTES


class SafeFetcher:
    def __init__(
        self, *, resolver: Resolver = system_resolver,
        transport_factory: TransportFactory = pinned_transport,
        max_redirects: int | None = None,
    ) -> None:
        self.resolver = resolver
        self.transport_factory = transport_factory
        self.max_redirects = (
            config.FETCH_MAX_REDIRECTS if max_redirects is None else max_redirects)

    def get(
        self, url: str, *, params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> SafeResponse:
        current = normalize_url(url)
        initial_scheme = urlsplit(current).scheme
        hops: list[FetchHop] = []
        redirects = 0
        current_params = params

        while True:
            target = validate_url(current, self.resolver)
            transport = self.transport_factory(target)
            request_headers = {"User-Agent": config.FETCH_USER_AGENT}
            request_headers.update(dict(headers or {}))
            # Automatyczna dekompresja może przydzielić ogromny pojedynczy
            # chunk zanim kod zdąży policzyć bajty. Żądamy identity i odrzucamy
            # serwer, który mimo tego zwraca kodowanie treści.
            request_headers["Accept-Encoding"] = "identity"
            with httpx.Client(
                transport=transport, follow_redirects=False, trust_env=False,
                timeout=timeout or config.FETCH_TIMEOUT_S,
            ) as client:
                with client.stream(
                    "GET", target.url, params=current_params,
                    headers=request_headers,
                ) as response:
                    actual_url = str(response.url)
                    hops.append(FetchHop(
                        actual_url, target.hostname, target.ips,
                        response.status_code))
                    current_params = None
                    if response.status_code in REDIRECT_STATUSES:
                        location = response.headers.get("location")
                        if not location:
                            raise RedirectPolicyError(
                                f"HTTP {response.status_code} bez Location")
                        redirects += 1
                        if redirects > self.max_redirects:
                            raise RedirectPolicyError(
                                f"więcej niż {self.max_redirects} redirectów")
                        next_url = normalize_url(urljoin(actual_url, location))
                        if (initial_scheme == "https"
                                and urlsplit(next_url).scheme != "https"):
                            raise RedirectPolicyError("downgrade HTTPS do HTTP")
                        current = next_url
                        continue

                    response_headers = {
                        key.lower(): value for key, value in response.headers.items()}
                    content_encoding = response_headers.get(
                        "content-encoding", "identity").strip().lower()
                    if content_encoding not in {"", "identity"}:
                        raise SafeFetchError(
                            f"skompresowana odpowiedź {content_encoding!r} "
                            "jest zabroniona")
                    limit = _limit_for(response_headers, actual_url)
                    length = response_headers.get("content-length")
                    if length:
                        try:
                            declared = int(length)
                        except ValueError:
                            declared = 0
                        if declared > limit:
                            raise ResponseTooLarge(
                                f"Content-Length {declared} > limit {limit}")
                    body = bytearray()
                    for chunk in response.iter_raw():
                        if len(body) + len(chunk) > limit:
                            raise ResponseTooLarge(
                                f"strumień przekroczył limit {limit} bajtów")
                        body.extend(chunk)
                    return SafeResponse(
                        response.status_code, response_headers, bytes(body),
                        actual_url, tuple(hops))


def get(url: str, **kwargs: Any) -> SafeResponse:
    return SafeFetcher().get(url, **kwargs)

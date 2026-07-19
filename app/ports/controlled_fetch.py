"""Controlled Fetch — realny adapter FetchPort z jawną granicą zaufania (E2-B).

Warstwa zawiera trzy zamknięte elementy:

1. **Deterministyczna polityka adresów** (`validate_url_syntax` /
   `validate_url_boundary`): kontrola granicy adresu PRZED konstrukcją
   requestu — schematy, credentials, host, port, zakresy adresów. Nazwy hostów
   klasyfikuje wyłącznie wstrzykiwany resolver; moduł sam nigdy nie wykonuje
   DNS. To nie jest ogólny system filtrowania internetu — wyłącznie granica
   jednego kontrolowanego pobrania.
2. **Wstrzykiwalny transport HTTP**: `FakeControlledHttpTransport` (testy)
   oraz `RealControlledHttpTransport` (urllib; bez proxy z ENV, bez cookies,
   bez credentials, bez automatycznych przekierowań). W fali E2-B realny
   transport nie jest nigdzie wykonywany.
3. **Adapter `ControlledHttpFetch`** implementujący istniejący `FetchPort`:
   przyjmuje wyłącznie jawny URL z trwałego intentu, egzekwuje timeout,
   twardy limit bajtów, limit przekierowań i allowlistę typów treści; zwraca
   typowany `FetchedDocument` (wynik albo kontrolowany kod błędu, nigdy
   sekrety).
"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Callable, Protocol
from urllib.parse import urljoin, urlsplit

from app.core.clock import Clock
from app.ports.fetch import FetchedDocument

SUPPORTED_URL_SCHEMES = ("http", "https")
# Zamknięta polityka portów v1: wyłącznie domyślne porty http/https.
ALLOWED_EXPLICIT_PORTS = (80, 443)

# Resolver: hostname -> krotka tekstowych adresów IP; OSError = brak rozwiązania.
AddressResolver = Callable[[str], tuple[str, ...]]


@dataclass(frozen=True)
class UrlPolicyDecision:
    allowed: bool
    code: str
    detail: str = ""

    @staticmethod
    def ok() -> "UrlPolicyDecision":
        return UrlPolicyDecision(True, "OK")

    @staticmethod
    def rejected(code: str, detail: str = "") -> "UrlPolicyDecision":
        return UrlPolicyDecision(False, code, detail)


def _classify_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str | None:
    """Return the first violated boundary code for one already-parsed address."""
    if address.is_unspecified:
        return "ADDRESS_UNSPECIFIED"
    if address.is_loopback:
        return "ADDRESS_LOOPBACK"
    if address.is_link_local:
        return "ADDRESS_LINK_LOCAL"
    if address.is_multicast:
        return "ADDRESS_MULTICAST"
    # 240.0.0.0/4 jest w Pythonie jednocześnie reserved i private; kolejność
    # przyznaje dokładniejszą etykietę zakresowi IANA-reserved.
    if address.is_reserved:
        return "ADDRESS_RESERVED"
    if address.is_private:
        return "ADDRESS_PRIVATE"
    if not address.is_global:
        return "ADDRESS_NOT_GLOBAL"
    return None


def validate_url_syntax(url: str) -> UrlPolicyDecision:
    """Deterministic pre-request boundary that needs no resolver at all."""
    if not isinstance(url, str) or not url.strip() or url != url.strip():
        return UrlPolicyDecision.rejected("URL_MALFORMED", "empty or whitespace-edged URL")
    try:
        parts = urlsplit(url)
    except ValueError:
        return UrlPolicyDecision.rejected("URL_MALFORMED", "URL cannot be parsed")
    if parts.scheme.lower() not in SUPPORTED_URL_SCHEMES:
        return UrlPolicyDecision.rejected(
            "URL_SCHEME_UNSUPPORTED", f"scheme={parts.scheme or '<none>'}"
        )
    if parts.username is not None or parts.password is not None:
        return UrlPolicyDecision.rejected(
            "URL_CREDENTIALS_FORBIDDEN", "userinfo is never allowed"
        )
    try:
        hostname = parts.hostname
        port = parts.port
    except ValueError:
        return UrlPolicyDecision.rejected("URL_HOST_INVALID", "host or port cannot be parsed")
    if not hostname:
        return UrlPolicyDecision.rejected("URL_HOST_MISSING", "URL has no host")
    if port is not None and port not in ALLOWED_EXPLICIT_PORTS:
        return UrlPolicyDecision.rejected("URL_PORT_UNSUPPORTED", f"port={port}")
    lowered = hostname.lower().rstrip(".")
    if lowered == "localhost" or lowered.endswith(".localhost"):
        return UrlPolicyDecision.rejected("ADDRESS_LOOPBACK", "localhost name")
    return UrlPolicyDecision.ok()


def validate_url_boundary(url: str, *, resolver: AddressResolver) -> UrlPolicyDecision:
    """Full address boundary: syntax plus range classification of every address.

    Literal IP hosts are classified directly; hostnames only through the
    injected resolver. Every returned address must independently pass — one
    disallowed address rejects the whole URL (fail-closed).
    """
    syntactic = validate_url_syntax(url)
    if not syntactic.allowed:
        return syntactic
    hostname = urlsplit(url).hostname
    assert hostname is not None
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        code = _classify_address(literal)
        if code is not None:
            return UrlPolicyDecision.rejected(code, f"literal address {hostname}")
        return UrlPolicyDecision.ok()
    try:
        resolved = resolver(hostname)
    except OSError as exc:
        return UrlPolicyDecision.rejected("DNS_RESOLUTION_FAILED", type(exc).__name__)
    if not resolved:
        return UrlPolicyDecision.rejected("DNS_RESOLUTION_FAILED", "resolver returned no address")
    for item in resolved:
        try:
            address = ipaddress.ip_address(item)
        except ValueError:
            return UrlPolicyDecision.rejected("DNS_RESOLUTION_FAILED", "resolver returned a non-address")
        code = _classify_address(address)
        if code is not None:
            return UrlPolicyDecision.rejected(code, f"resolved address for {hostname}")
    return UrlPolicyDecision.ok()


def default_address_resolver(hostname: str) -> tuple[str, ...]:
    """Realny resolver systemowy — nigdy nie wywoływany w testach.

    Safety kernel testów blokuje ``socket.getaddrinfo``, więc każde omyłkowe
    użycie w teście kończy się twardym, jawnym błędem (fail-closed).
    """
    import socket

    infos = socket.getaddrinfo(hostname, None)
    return tuple(dict.fromkeys(str(info[4][0]) for info in infos))


@dataclass(frozen=True)
class TransportResponse:
    """Typowany, zamknięty wynik jednego żądania transportu."""

    status: int
    content_type: str | None
    location: str | None
    body: bytes
    body_complete: bool


class ControlledFetchTransportError(RuntimeError):
    """Typowany błąd transportu; ``code`` jest kontrolowany i wolny od sekretów."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        super().__init__(code if not detail else f"{code}: {detail}")


class ControlledHttpTransport(Protocol):
    def request(
        self, url: str, *, timeout_seconds: int, max_read_bytes: int,
    ) -> TransportResponse: ...


class FakeControlledHttpTransport:
    """Deterministyczny transport in-memory dla testów — zero sieci."""

    def __init__(self, responses: dict[str, TransportResponse] | None = None) -> None:
        self._responses: dict[str, TransportResponse] = dict(responses or {})
        self.calls: list[dict[str, object]] = []

    def register(self, url: str, response: TransportResponse) -> None:
        self._responses[url] = response

    @classmethod
    def from_fixture(cls, data: dict) -> "FakeControlledHttpTransport":
        responses: dict[str, TransportResponse] = {}
        for url, raw in dict(data.get("responses") or {}).items():
            body = raw.get("body_utf8", "")
            responses[url] = TransportResponse(
                status=int(raw["status"]),
                content_type=raw.get("content_type"),
                location=raw.get("location"),
                body=body.encode("utf-8") if isinstance(body, str) else bytes(body),
                body_complete=bool(raw.get("body_complete", True)),
            )
        return cls(responses)

    def request(
        self, url: str, *, timeout_seconds: int, max_read_bytes: int,
    ) -> TransportResponse:
        self.calls.append({
            "url": url, "timeout_seconds": timeout_seconds,
            "max_read_bytes": max_read_bytes,
        })
        response = self._responses.get(url)
        if response is None:
            raise ControlledFetchTransportError(
                "FAKE_URL_NOT_REGISTERED", "fake transport has no scripted response"
            )
        if len(response.body) > max_read_bytes:
            # Prawdziwy transport nigdy nie odda więcej niż limit; fake odwzorowuje
            # ten kontrakt zamiast pozwalać fixture'owi go ominąć.
            return TransportResponse(
                status=response.status, content_type=response.content_type,
                location=response.location, body=response.body[:max_read_bytes],
                body_complete=False,
            )
        return response


def fake_resolver_from_fixture(data: dict) -> AddressResolver:
    """Resolver zbudowany wyłącznie z jawnie podstawionych danych fixture."""
    table = {
        str(host).lower(): tuple(str(item) for item in addresses)
        for host, addresses in dict(data.get("resolved_addresses") or {}).items()
    }

    def resolve(hostname: str) -> tuple[str, ...]:
        resolved = table.get(hostname.lower())
        if resolved is None:
            raise OSError(f"fake resolver has no entry for {hostname!r}")
        return resolved

    return resolve


class RealControlledHttpTransport:
    """Prawdziwy transport urllib — kod istnieje, ale w E2-B nie jest wykonywany.

    Kontrakt: metoda GET; ``ProxyHandler({})`` odcina proxy z ENV; brak cookie
    processora i brak handlerów auth = zero cookies i zero credentials; brak
    automatycznego podążania za przekierowaniami (3xx wraca jako typowana
    odpowiedź z ``location``); odczyt zatrzymuje się na ``max_read_bytes``.
    Znane ograniczenie (ADR): polityka adresów klasyfikuje adresy przed
    requestem, a urllib wykonuje własną resolucję nazwy przy połączeniu —
    okno TOCTOU DNS pozostaje jawnie otwarte do zamknięcia przed pierwszym
    realnym użyciem.
    """

    _USER_AGENT = "nia-controlled-fetch/1"

    def request(
        self, url: str, *, timeout_seconds: int, max_read_bytes: int,
    ) -> TransportResponse:
        import socket
        import urllib.error
        import urllib.request

        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        opener = urllib.request.build_opener(
            _NoRedirect(), urllib.request.ProxyHandler({}),
        )
        request = urllib.request.Request(
            url, method="GET",
            headers={"User-Agent": self._USER_AGENT, "Accept": "text/html, text/plain"},
        )
        try:
            try:
                response = opener.open(request, timeout=timeout_seconds)
            except urllib.error.HTTPError as exc:
                # 3xx/4xx/5xx z nagłówkami — to nadal typowana odpowiedź HTTP.
                response = exc
            with response:
                status = int(getattr(response, "status", None) or response.getcode())
                content_type = response.headers.get("Content-Type")
                location = response.headers.get("Location")
                body = response.read(max_read_bytes)
                body_complete = len(response.read(1)) == 0
            return TransportResponse(
                status=status, content_type=content_type, location=location,
                body=body, body_complete=body_complete,
            )
        except (socket.timeout, TimeoutError) as exc:
            raise ControlledFetchTransportError("TIMEOUT") from exc
        except urllib.error.URLError as exc:
            raise ControlledFetchTransportError(
                "CONNECTION_FAILED", type(getattr(exc, "reason", exc)).__name__
            ) from exc
        except OSError as exc:
            raise ControlledFetchTransportError("CONNECTION_FAILED", type(exc).__name__) from exc


@dataclass(frozen=True)
class ControlledFetchRequestContract:
    """Zamrożony wycinek intentu potrzebny adapterowi — nic ponad jedno pobranie."""

    requested_url: str
    timeout_seconds: int
    max_bytes: int
    max_redirects: int
    allowed_content_types: tuple[str, ...]


class ControlledFetchContractViolation(RuntimeError):
    """Adapter został użyty poza swoim zamrożonym kontraktem (błąd programu)."""


def _media_type(content_type: str | None) -> str | None:
    if content_type is None:
        return None
    media = content_type.split(";", 1)[0].strip().lower()
    return media or None


class ControlledHttpFetch:
    """Realny adapter `FetchPort` dla dokładnie jednego zatwierdzonego URL.

    Konstruktor wymaga JAWNEGO transportu i resolvera — nie istnieje żaden
    domyślny transport, więc test bez fake transportu nie może zbudować
    adaptera. Wynik jest zawsze typowany: `FetchedDocument` z treścią albo
    z kontrolowanym kodem błędu w polu ``error``.
    """

    def __init__(
        self, *, contract: ControlledFetchRequestContract,
        transport: ControlledHttpTransport, resolver: AddressResolver,
        clock: Clock,
    ) -> None:
        self._contract = contract
        self._transport = transport
        self._resolver = resolver
        self._clock = clock

    def preflight_boundary(self) -> UrlPolicyDecision:
        """Pełna kontrola granicy adresu dla zamrożonego URL — bez transportu."""
        return validate_url_boundary(
            self._contract.requested_url, resolver=self._resolver,
        )

    def _error_document(self, final_url: str, code: str) -> FetchedDocument:
        return FetchedDocument(
            requested_url=self._contract.requested_url, final_url=final_url,
            fetched_at=self._clock.now(), http_status=None, content_type=None,
            body=b"", error=code,
        )

    def fetch(self, url: str) -> FetchedDocument:
        contract = self._contract
        if url != contract.requested_url:
            raise ControlledFetchContractViolation(
                "ControlledHttpFetch accepts only the exact frozen intent URL."
            )
        current_url = contract.requested_url
        redirects_used = 0
        while True:
            decision = validate_url_boundary(current_url, resolver=self._resolver)
            if not decision.allowed:
                prefix = "URL_POLICY_REJECTED" if redirects_used == 0 else "REDIRECT_POLICY_REJECTED"
                return self._error_document(current_url, f"{prefix}:{decision.code}")
            try:
                response = self._transport.request(
                    current_url,
                    timeout_seconds=contract.timeout_seconds,
                    max_read_bytes=contract.max_bytes,
                )
            except ControlledFetchTransportError as exc:
                return self._error_document(current_url, exc.code)
            if 300 <= response.status < 400 and response.location:
                redirects_used += 1
                if redirects_used > contract.max_redirects:
                    return self._error_document(current_url, "TOO_MANY_REDIRECTS")
                current_url = urljoin(current_url, response.location)
                continue
            if not response.body_complete:
                return self._error_document(current_url, "RESPONSE_TOO_LARGE")
            media = _media_type(response.content_type)
            if 200 <= response.status < 300 and media not in contract.allowed_content_types:
                return self._error_document(
                    current_url, f"CONTENT_TYPE_REJECTED:{media or 'missing'}"
                )
            return FetchedDocument(
                requested_url=contract.requested_url, final_url=current_url,
                fetched_at=self._clock.now(), http_status=response.status,
                content_type=response.content_type, body=response.body, error=None,
            )

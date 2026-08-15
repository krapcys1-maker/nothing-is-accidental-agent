"""Controlled Fetch — adapter FetchPort z przypiętym celem połączenia (E2-C).

Warstwa zawiera trzy zamknięte elementy:

1. **Deterministyczna polityka adresów** (`validate_url_syntax` /
   `validate_url_boundary`): kontrola granicy adresu PRZED konstrukcją
   requestu — schematy, credentials, host, port, zakresy adresów. Nazwy hostów
   klasyfikuje wyłącznie wstrzykiwany resolver; moduł sam nigdy nie wykonuje
   DNS. To nie jest ogólny system filtrowania internetu — wyłącznie granica
   jednego kontrolowanego pobrania.
2. **Immutable host binding**: dokładny adres używany przez transport pochodzi
   z tego samego, jednorazowego rozstrzygnięcia, które przeszło politykę.
   Transport nie otrzymuje hostname do ponownej resolucji.
3. **Wstrzykiwalny transport HTTP**: publiczny fake dla testów oraz prywatny
   transport realny budowany wyłącznie przez factory wymagające capability
   wydanej przez storage po zużyciu approvalu L1.
4. **Adapter `ControlledHttpFetch`** implementujący istniejący `FetchPort`:
   przyjmuje wyłącznie jawny URL z trwałego intentu, egzekwuje timeout,
   twardy limit bajtów, limit przekierowań i allowlistę typów treści; zwraca
   typowany `FetchedDocument` (wynik albo kontrolowany kod błędu, nigdy
   sekrety).
"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Callable, Protocol
from urllib.parse import urljoin, urlsplit, urlunsplit

from app.core.clock import Clock
from app.models import ControlledFetchTransportAuthorization
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


@dataclass(frozen=True)
class BoundHttpTarget:
    """Immutable URL→address binding consumed directly by a transport.

    `selected_address` is numeric and has already passed the local policy.
    `host_header` and `tls_server_name` preserve the original HTTP/TLS
    identity while the socket connects only to the selected numeric address.
    """

    url: str
    scheme: str
    hostname: str
    port: int
    selected_address: str
    approved_addresses: tuple[str, ...]
    request_target: str
    host_header: str
    tls_server_name: str | None


@dataclass(frozen=True)
class UrlTargetBinding:
    decision: UrlPolicyDecision
    target: BoundHttpTarget | None = None


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


def bind_url_target(url: str, *, resolver: AddressResolver) -> UrlTargetBinding:
    """Validate and pin one exact numeric connection target.

    Hostnames are resolved exactly once for this binding. Every returned
    address must pass; the deterministic first address (IP version + packed
    bytes ordering) becomes the socket target. The complete approved set stays
    in the immutable binding for audit and validation.
    """
    syntactic = validate_url_syntax(url)
    if not syntactic.allowed:
        return UrlTargetBinding(syntactic)
    parts = urlsplit(url)
    hostname = parts.hostname
    assert hostname is not None
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        code = _classify_address(literal)
        if code is not None:
            return UrlTargetBinding(
                UrlPolicyDecision.rejected(code, f"literal address {hostname}")
            )
        addresses = (literal,)
    else:
        try:
            resolved = resolver(hostname)
        except OSError as exc:
            return UrlTargetBinding(
                UrlPolicyDecision.rejected(
                    "DNS_RESOLUTION_FAILED", type(exc).__name__
                )
            )
        if not resolved:
            return UrlTargetBinding(
                UrlPolicyDecision.rejected(
                    "DNS_RESOLUTION_FAILED", "resolver returned no address"
                )
            )
        parsed: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
        seen: set[tuple[int, bytes]] = set()
        for item in resolved:
            try:
                address = ipaddress.ip_address(item)
            except ValueError:
                return UrlTargetBinding(
                    UrlPolicyDecision.rejected(
                        "DNS_RESOLUTION_FAILED",
                        "resolver returned a non-address",
                    )
                )
            code = _classify_address(address)
            if code is not None:
                return UrlTargetBinding(
                    UrlPolicyDecision.rejected(
                        code, f"resolved address for {hostname}"
                    )
                )
            key = (address.version, address.packed)
            if key not in seen:
                seen.add(key)
                parsed.append(address)
        if not parsed:
            return UrlTargetBinding(
                UrlPolicyDecision.rejected(
                    "DNS_RESOLUTION_FAILED", "resolver returned no usable address"
                )
            )
        addresses = tuple(parsed)

    ordered = tuple(sorted(addresses, key=lambda item: (item.version, item.packed)))
    canonical_addresses = tuple(str(item) for item in ordered)
    selected = canonical_addresses[0]
    scheme = parts.scheme.lower()
    port = parts.port if parts.port is not None else (443 if scheme == "https" else 80)
    host_for_header = f"[{hostname}]" if ":" in hostname else hostname
    host_header = (
        f"{host_for_header}:{port}" if parts.port is not None else host_for_header
    )
    request_target = urlunsplit(("", "", parts.path or "/", parts.query, ""))
    target = BoundHttpTarget(
        url=url,
        scheme=scheme,
        hostname=hostname,
        port=port,
        selected_address=selected,
        approved_addresses=canonical_addresses,
        request_target=request_target,
        host_header=host_header,
        tls_server_name=hostname if scheme == "https" else None,
    )
    try:
        _validate_bound_target(target)
    except ControlledFetchTransportError as exc:
        return UrlTargetBinding(
            UrlPolicyDecision.rejected(exc.code, "bound target is inconsistent")
        )
    return UrlTargetBinding(UrlPolicyDecision.ok(), target)


def validate_url_boundary(url: str, *, resolver: AddressResolver) -> UrlPolicyDecision:
    """Compatibility policy view over the immutable binding operation."""
    return bind_url_target(url, resolver=resolver).decision


def _validate_bound_target(target: BoundHttpTarget) -> None:
    """Reject a forged or internally inconsistent transport binding without DNS."""
    syntactic = validate_url_syntax(target.url)
    if not syntactic.allowed:
        raise ControlledFetchTransportError(
            "BOUND_TARGET_INVALID", syntactic.code,
        )
    parts = urlsplit(target.url)
    hostname = parts.hostname
    if hostname is None:
        raise ControlledFetchTransportError("BOUND_TARGET_INVALID", "missing host")
    scheme = parts.scheme.lower()
    port = parts.port if parts.port is not None else (443 if scheme == "https" else 80)
    host_for_header = f"[{hostname}]" if ":" in hostname else hostname
    expected_host_header = (
        f"{host_for_header}:{port}" if parts.port is not None else host_for_header
    )
    expected_request_target = urlunsplit(
        ("", "", parts.path or "/", parts.query, "")
    )
    expected_tls_name = hostname if scheme == "https" else None
    if (
        target.scheme != scheme
        or target.hostname != hostname
        or target.port != port
        or target.host_header != expected_host_header
        or target.request_target != expected_request_target
        or target.tls_server_name != expected_tls_name
        or not target.approved_addresses
        or target.selected_address != target.approved_addresses[0]
    ):
        raise ControlledFetchTransportError(
            "BOUND_TARGET_INVALID", "host, SNI, port or request target mismatch"
        )
    parsed_addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for item in target.approved_addresses:
        try:
            address = ipaddress.ip_address(item)
        except ValueError:
            raise ControlledFetchTransportError(
                "BOUND_TARGET_INVALID", "approved address is not numeric"
            )
        code = _classify_address(address)
        if code is not None:
            raise ControlledFetchTransportError(
                "BOUND_TARGET_INVALID", f"approved address violates {code}"
            )
        if str(address) != item:
            raise ControlledFetchTransportError(
                "BOUND_TARGET_INVALID", "approved address is not canonical"
            )
        parsed_addresses.append(address)
    expected_addresses = tuple(
        str(item)
        for item in sorted(
            set(parsed_addresses),
            key=lambda item: (item.version, item.packed),
        )
    )
    if target.approved_addresses != expected_addresses:
        raise ControlledFetchTransportError(
            "BOUND_TARGET_INVALID",
            "approved address set is duplicated or non-deterministic",
        )


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
        self, target: BoundHttpTarget, *, timeout_seconds: int, max_read_bytes: int,
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
        self, target: BoundHttpTarget, *, timeout_seconds: int, max_read_bytes: int,
    ) -> TransportResponse:
        _validate_bound_target(target)
        self.calls.append({
            "url": target.url,
            "selected_address": target.selected_address,
            "approved_addresses": target.approved_addresses,
            "host_header": target.host_header,
            "tls_server_name": target.tls_server_name,
            "request_target": target.request_target,
            "timeout_seconds": timeout_seconds,
            "max_read_bytes": max_read_bytes,
        })
        response = self._responses.get(target.url)
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


_REAL_TRANSPORT_CONSTRUCTOR_SEAL = object()


class _RealControlledHttpTransport:
    """Minimalny transport łączący się wyłącznie z przypiętym adresem IP.

    Konstruktor wymaga prywatnej pieczęci wspieranego factory. Właściwą
    barierą runtime factory jest capability wydana przez storage dopiero po
    zużyciu zgody L1. Transport nie używa proxy, cookies ani automatycznych
    przekierowań i nigdy nie rozwiązuje nazwy hosta. Oryginalna tożsamość
    pozostaje w nagłówku Host oraz TLS SNI.
    """

    _USER_AGENT = "nia-controlled-fetch/1"

    def __init__(self, *, _seal: object) -> None:
        if _seal is not _REAL_TRANSPORT_CONSTRUCTOR_SEAL:
            raise TypeError(
                "Real controlled transport can only be built by the authorized factory."
            )

    def request(
        self,
        target: BoundHttpTarget,
        *,
        timeout_seconds: int,
        max_read_bytes: int,
    ) -> TransportResponse:
        import http.client
        import socket
        import ssl

        _validate_bound_target(target)
        address = ipaddress.ip_address(target.selected_address)
        family = socket.AF_INET6 if address.version == 6 else socket.AF_INET
        connect_address: tuple[object, ...]
        if address.version == 6:
            connect_address = (target.selected_address, target.port, 0, 0)
        else:
            connect_address = (target.selected_address, target.port)

        raw_socket = None
        stream = None
        connection = None
        try:
            raw_socket = socket.socket(family, socket.SOCK_STREAM)
            raw_socket.settimeout(timeout_seconds)
            raw_socket.connect(connect_address)
            stream = raw_socket
            if target.scheme == "https":
                context = ssl.create_default_context()
                stream = context.wrap_socket(
                    raw_socket,
                    server_hostname=target.tls_server_name,
                )
            connection = http.client.HTTPConnection(
                target.hostname,
                target.port,
                timeout=timeout_seconds,
            )
            connection.sock = stream
            connection.request(
                "GET",
                target.request_target,
                headers={
                    "Host": target.host_header,
                    "User-Agent": self._USER_AGENT,
                    "Accept": "text/html, text/plain",
                    "Connection": "close",
                },
            )
            response = connection.getresponse()
            body_with_sentinel = response.read(max_read_bytes + 1)
            return TransportResponse(
                status=int(response.status),
                content_type=response.getheader("Content-Type"),
                location=response.getheader("Location"),
                body=body_with_sentinel[:max_read_bytes],
                body_complete=len(body_with_sentinel) <= max_read_bytes,
            )
        except (socket.timeout, TimeoutError) as exc:
            raise ControlledFetchTransportError("TIMEOUT") from exc
        except (http.client.HTTPException, ssl.SSLError, OSError) as exc:
            raise ControlledFetchTransportError(
                "CONNECTION_FAILED", type(exc).__name__
            ) from exc
        finally:
            if connection is not None:
                connection.close()
            elif stream is not None:
                stream.close()
            elif raw_socket is not None:
                raw_socket.close()


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


def build_real_controlled_fetch_port(
    authorization: ControlledFetchTransportAuthorization,
    *,
    clock: Clock,
) -> "ControlledHttpFetch":
    """Build the live adapter only from a storage-issued, consumed approval."""
    authorization.assert_usable_at(clock.now())
    contract = ControlledFetchRequestContract(
        requested_url=authorization.requested_url,
        timeout_seconds=authorization.timeout_seconds,
        max_bytes=authorization.max_bytes,
        max_redirects=authorization.max_redirects,
        allowed_content_types=authorization.allowed_content_types,
    )
    return ControlledHttpFetch(
        contract=contract,
        transport=_RealControlledHttpTransport(
            _seal=_REAL_TRANSPORT_CONSTRUCTOR_SEAL,
        ),
        resolver=default_address_resolver,
        clock=clock,
    )


def _media_type(content_type: str | None) -> str | None:
    if content_type is None:
        return None
    media = content_type.split(";", 1)[0].strip().lower()
    return media or None


# Phrases a site uses to say it is refusing automated access. Taken from the
# page eCFR actually served us, which said so in as many words: "programmatic
# access to these sites is limited to access to our extensive developer APIs",
# "Your request has been flagged as potentially automated", "complete the
# CAPTCHA (bot test)".
#
# Matching the words rather than guessing from size and redirects, because the
# guess had a false positive on an ordinary cross-host redirect and this does
# not. It reports the refusal so the source is not counted; it never works
# around one. A host that offers an API for programmatic access is telling us
# the supported route, and scraping past the check is not it.
_REFUSAL_PHRASES = (
    "you have been blocked",
    "access denied",
    "are you a robot",
    "verify you are human",
    "enable javascript and cookies",
    "unusual traffic",
    "captcha",
    "request has been flagged",
    "programmatic access to these sites is limited",
)


def _blocked_page_reason(
    *, requested_url: str, final_url: str, body: bytes | str | None,
) -> str | None:
    """Name the refusal when a 200 response is a challenge, not a document."""
    del requested_url, final_url
    if body is None:
        return None
    text = body.decode("utf-8", "replace") if isinstance(body, bytes) else body
    if any(phrase in text.lower() for phrase in _REFUSAL_PHRASES):
        return "FETCH_REFUSED_BY_HOST"
    return None


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
        self._initial_binding: UrlTargetBinding | None = None

    def preflight_boundary(self) -> UrlPolicyDecision:
        """Resolve, validate and cache the exact initial connection target."""
        if self._initial_binding is None:
            self._initial_binding = bind_url_target(
                self._contract.requested_url,
                resolver=self._resolver,
            )
        return self._initial_binding.decision

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
        if self._initial_binding is None:
            self.preflight_boundary()
        assert self._initial_binding is not None
        if (
            not self._initial_binding.decision.allowed
            or self._initial_binding.target is None
        ):
            return self._error_document(
                contract.requested_url,
                f"URL_POLICY_REJECTED:{self._initial_binding.decision.code}",
            )
        current_target = self._initial_binding.target
        redirects_used = 0
        while True:
            try:
                response = self._transport.request(
                    current_target,
                    timeout_seconds=contract.timeout_seconds,
                    max_read_bytes=contract.max_bytes,
                )
            except ControlledFetchTransportError as exc:
                return self._error_document(current_target.url, exc.code)
            if 300 <= response.status < 400 and response.location:
                redirects_used += 1
                if redirects_used > contract.max_redirects:
                    return self._error_document(
                        current_target.url,
                        "TOO_MANY_REDIRECTS",
                    )
                redirect_url = urljoin(current_target.url, response.location)
                redirect_binding = bind_url_target(
                    redirect_url,
                    resolver=self._resolver,
                )
                if (
                    not redirect_binding.decision.allowed
                    or redirect_binding.target is None
                ):
                    return self._error_document(
                        redirect_url,
                        "REDIRECT_POLICY_REJECTED:"
                        f"{redirect_binding.decision.code}",
                    )
                current_target = redirect_binding.target
                continue
            if not response.body_complete:
                return self._error_document(
                    current_target.url,
                    "RESPONSE_TOO_LARGE",
                )
            media = _media_type(response.content_type)
            if 200 <= response.status < 300 and media not in contract.allowed_content_types:
                return self._error_document(
                    current_target.url,
                    f"CONTENT_TYPE_REJECTED:{media or 'missing'}",
                )
            # A site that blocks automated access answers 200 with a challenge
            # page, so HTTP status alone reports success for a document we were
            # refused. Five eCFR requests in one run redirected to
            # unblock.federalregister.gov and each stored 1,096 characters of
            # "you have been blocked"; the run reported ten successful fetches
            # and the corpus held one usable source.
            #
            # A refusal we cannot read is a failed fetch and is recorded as one.
            # It is NOT worked around: we do not retry with another identity, we
            # do not evade the check, and a host that declines automated access
            # is simply a host this corpus cannot use.
            if 200 <= response.status < 300:
                block = _blocked_page_reason(
                    requested_url=contract.requested_url,
                    final_url=current_target.url,
                    body=response.body,
                )
                if block is not None:
                    return self._error_document(current_target.url, block)
            return FetchedDocument(
                requested_url=contract.requested_url,
                final_url=current_target.url,
                fetched_at=self._clock.now(), http_status=response.status,
                content_type=response.content_type, body=response.body, error=None,
            )

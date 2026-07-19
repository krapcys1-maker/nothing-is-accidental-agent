"""E2-C counterprobes: runtime gate, storage capability and DNS host binding.

All tests are offline. The real transport is exercised only with in-memory
socket/TLS/HTTP doubles; no resolver, socket or HTTP operation leaves pytest.
"""
from __future__ import annotations

import http.client
import inspect
import socket
import ssl
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.clock import FixedClock
from app.core.config import Settings
from app.models import (
    ControlledFetchTransportAuthorization,
    _issue_controlled_fetch_transport_authorization,
)
from app.ports import controlled_fetch as controlled_fetch_module
from app.ports.controlled_fetch import (
    ControlledFetchRequestContract,
    ControlledFetchTransportError,
    ControlledHttpFetch,
    FakeControlledHttpTransport,
    TransportResponse,
    bind_url_target,
    build_real_controlled_fetch_port,
)
from app.research.controlled_fetch_intent import ControlledFetchIntent
from app.workflows.research.controlled_fetch import resolve_controlled_fetch_port

NOW = datetime(2026, 7, 19, 12, 0, 0, tzinfo=timezone.utc)
CLOCK = FixedClock(NOW)
INITIAL_URL = "https://example.com/report?q=1"
REDIRECT_URL = "https://www.example.org/final"
INITIAL_IP = "93.184.216.34"
ALTERNATE_IP = "142.250.72.14"
REDIRECT_IP = "151.101.1.69"


def _intent() -> ControlledFetchIntent:
    return ControlledFetchIntent.build(
        account_id="nothing_is_accidental",
        topic_id=19,
        source_identity="e2c-test-source",
        requested_url=INITIAL_URL,
        timeout_seconds=11,
        max_bytes=20_000,
        max_redirects=2,
        allowed_content_types=["text/html", "text/plain"],
        requested_at=NOW,
        expires_at=NOW + timedelta(hours=2),
    )


def _authorization(
    intent: ControlledFetchIntent | None = None,
) -> ControlledFetchTransportAuthorization:
    intent = intent or _intent()
    return _issue_controlled_fetch_transport_authorization(
        job_id="job-e2c",
        run_id="run-e2c",
        account_id=intent.account_id,
        topic_id=intent.topic_id,
        approval_id=7,
        attempt_id=8,
        requested_url=intent.requested_url,
        source_identity=intent.source_identity,
        intent_fingerprint=intent.fingerprint,
        timeout_seconds=intent.timeout_seconds,
        max_bytes=intent.max_bytes,
        max_redirects=intent.max_redirects,
        allowed_content_types=tuple(intent.allowed_content_types),
        approval_expires_at=NOW + timedelta(hours=1),
    )


def _settings(*, real_enabled: bool) -> Settings:
    return Settings(
        project_root=Path("."),
        data_dir=Path("."),
        db_path=Path("test.db"),
        costs_csv_path=Path("costs.csv"),
        controlled_fetch_real_enabled=real_enabled,
    )


def _contract() -> ControlledFetchRequestContract:
    intent = _intent()
    return ControlledFetchRequestContract(
        requested_url=intent.requested_url,
        timeout_seconds=intent.timeout_seconds,
        max_bytes=intent.max_bytes,
        max_redirects=intent.max_redirects,
        allowed_content_types=tuple(intent.allowed_content_types),
    )


def test_initial_host_is_resolved_once_and_exact_selected_ip_reaches_transport():
    resolver_calls: list[str] = []

    def resolver(hostname: str) -> tuple[str, ...]:
        resolver_calls.append(hostname)
        return (ALTERNATE_IP, INITIAL_IP)

    transport = FakeControlledHttpTransport({
        INITIAL_URL: TransportResponse(
            status=200,
            content_type="text/html",
            location=None,
            body=b"ok",
            body_complete=True,
        ),
    })
    adapter = ControlledHttpFetch(
        contract=_contract(),
        transport=transport,
        resolver=resolver,
        clock=CLOCK,
    )

    assert adapter.preflight_boundary().allowed
    document = adapter.fetch(INITIAL_URL)

    assert document.error is None
    assert resolver_calls == ["example.com"]
    assert transport.calls == [{
        "url": INITIAL_URL,
        "selected_address": INITIAL_IP,
        "approved_addresses": (INITIAL_IP, ALTERNATE_IP),
        "host_header": "example.com",
        "tls_server_name": "example.com",
        "request_target": "/report?q=1",
        "timeout_seconds": 11,
        "max_read_bytes": 20_000,
    }]


def test_redirect_gets_one_new_binding_without_re_resolving_initial_host():
    resolver_calls: list[str] = []
    addresses = {
        "example.com": (INITIAL_IP,),
        "www.example.org": (REDIRECT_IP,),
    }

    def resolver(hostname: str) -> tuple[str, ...]:
        resolver_calls.append(hostname)
        return addresses[hostname]

    transport = FakeControlledHttpTransport({
        INITIAL_URL: TransportResponse(
            status=302,
            content_type=None,
            location=REDIRECT_URL,
            body=b"",
            body_complete=True,
        ),
        REDIRECT_URL: TransportResponse(
            status=200,
            content_type="text/plain",
            location=None,
            body=b"redirected",
            body_complete=True,
        ),
    })
    adapter = ControlledHttpFetch(
        contract=_contract(),
        transport=transport,
        resolver=resolver,
        clock=CLOCK,
    )

    document = adapter.fetch(INITIAL_URL)

    assert document.error is None
    assert document.final_url == REDIRECT_URL
    assert resolver_calls == ["example.com", "www.example.org"]
    assert [call["selected_address"] for call in transport.calls] == [
        INITIAL_IP,
        REDIRECT_IP,
    ]
    assert transport.calls[1]["host_header"] == "www.example.org"
    assert transport.calls[1]["tls_server_name"] == "www.example.org"


@pytest.mark.parametrize(
    ("resolved", "expected_code"),
    [
        ((), "DNS_RESOLUTION_FAILED"),
        (("not-an-ip",), "DNS_RESOLUTION_FAILED"),
        ((INITIAL_IP, "127.0.0.1"), "ADDRESS_LOOPBACK"),
        ((INITIAL_IP, "10.0.0.1"), "ADDRESS_PRIVATE"),
    ],
)
def test_binding_rejects_empty_invalid_or_partially_unsafe_resolution(
    resolved: tuple[str, ...],
    expected_code: str,
):
    binding = bind_url_target(
        INITIAL_URL,
        resolver=lambda _hostname: resolved,
    )
    assert not binding.decision.allowed
    assert binding.decision.code == expected_code
    assert binding.target is None


@pytest.mark.parametrize(
    "mutation",
    [
        lambda target: replace(target, approved_addresses=()),
        lambda target: replace(target, selected_address=ALTERNATE_IP),
        lambda target: replace(target, host_header="attacker.invalid"),
        lambda target: replace(target, tls_server_name="attacker.invalid"),
        lambda target: replace(
            target,
            approved_addresses=(ALTERNATE_IP, INITIAL_IP),
            selected_address=ALTERNATE_IP,
        ),
    ],
)
def test_transport_rejects_forged_or_inconsistent_binding(mutation):
    binding = bind_url_target(
        INITIAL_URL,
        resolver=lambda _hostname: (INITIAL_IP, ALTERNATE_IP),
    )
    assert binding.target is not None
    forged = mutation(binding.target)
    transport = FakeControlledHttpTransport()

    with pytest.raises(ControlledFetchTransportError) as caught:
        transport.request(
            forged,
            timeout_seconds=10,
            max_read_bytes=100,
        )
    assert caught.value.code == "BOUND_TARGET_INVALID"
    assert transport.calls == []


def test_direct_real_construction_and_forged_capability_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
):
    assert not hasattr(controlled_fetch_module, "RealControlledHttpTransport")
    with pytest.raises(TypeError, match="authorized factory"):
        controlled_fetch_module._RealControlledHttpTransport(_seal=object())

    valid = _authorization()
    forged = ControlledFetchTransportAuthorization(
        **{
            **valid.__dict__,
            "_seal": object(),
        },
    )
    monkeypatch.setenv("REAL_CONTROLLED_FETCH_ENABLED", "1")
    with pytest.raises(TypeError, match="issued by storage"):
        resolve_controlled_fetch_port(
            forged,
            settings=_settings(real_enabled=True),
            clock=CLOCK,
        )
    expired = replace(valid, approval_expires_at=NOW)
    with pytest.raises(TypeError, match="expired"):
        resolve_controlled_fetch_port(
            expired,
            settings=_settings(real_enabled=True),
            clock=CLOCK,
        )
    with pytest.raises(
        controlled_fetch_module.ControlledFetchContractViolation,
    ):
        build_real_controlled_fetch_port(valid, clock=CLOCK).fetch(
            "https://example.com/other",
        )


def test_authorized_construction_performs_no_dns_or_socket(
    monkeypatch: pytest.MonkeyPatch,
):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("construction crossed the network boundary")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    port = resolve_controlled_fetch_port(
        _authorization(),
        settings=_settings(real_enabled=True),
        clock=CLOCK,
    )
    assert isinstance(port, ControlledHttpFetch)


def test_real_transport_connects_to_numeric_ip_and_preserves_host_and_sni(
    monkeypatch: pytest.MonkeyPatch,
):
    events: dict[str, object] = {}

    class FakeSocket:
        def settimeout(self, timeout):
            events["socket_timeout"] = timeout

        def connect(self, address):
            events["connect"] = address

        def close(self):
            events["socket_closed"] = True

    class FakeTlsContext:
        def wrap_socket(self, stream, *, server_hostname):
            events["sni"] = server_hostname
            return stream

    class FakeResponse:
        status = 200

        @staticmethod
        def getheader(name):
            return {
                "Content-Type": "text/html",
                "Location": None,
            }[name]

        @staticmethod
        def read(_limit):
            return b"ok"

    class FakeConnection:
        def __init__(self, host, port, timeout):
            events["connection_identity"] = (host, port, timeout)
            self.sock = None

        def request(self, method, request_target, headers):
            events["request"] = (method, request_target, headers)

        @staticmethod
        def getresponse():
            return FakeResponse()

        @staticmethod
        def close():
            events["connection_closed"] = True

    monkeypatch.setattr(socket, "socket", lambda family, kind: FakeSocket())
    monkeypatch.setattr(ssl, "create_default_context", lambda: FakeTlsContext())
    monkeypatch.setattr(http.client, "HTTPConnection", FakeConnection)

    binding = bind_url_target(
        INITIAL_URL,
        resolver=lambda _hostname: (INITIAL_IP,),
    )
    assert binding.target is not None
    port = build_real_controlled_fetch_port(_authorization(), clock=CLOCK)
    response = port._transport.request(
        binding.target,
        timeout_seconds=11,
        max_read_bytes=20_000,
    )

    assert response.status == 200 and response.body == b"ok"
    assert events["connect"] == (INITIAL_IP, 443)
    assert events["sni"] == "example.com"
    assert events["connection_identity"] == ("example.com", 443, 11)
    method, request_target, headers = events["request"]
    assert method == "GET" and request_target == "/report?q=1"
    assert headers["Host"] == "example.com"
    assert headers["Connection"] == "close"


def test_real_transport_source_has_no_name_resolution_or_urllib_path():
    source = inspect.getsource(
        controlled_fetch_module._RealControlledHttpTransport.request,
    )
    assert "getaddrinfo" not in source
    assert "urllib" not in source
    assert "selected_address" in source
    assert "Proxy" not in source

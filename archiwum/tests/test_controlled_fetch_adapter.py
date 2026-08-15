"""E2-B unit tests: intent v1, lokalna polityka adresów, transporty i adapter.

Wszystko offline: fake transport, fake resolver, zero socketów (safety kernel
dodatkowo blokuje sieć dla całego procesu pytest — każda pomyłka = twardy błąd).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.clock import FixedClock
from app.core.config import Settings
from app.models import (
    EvidenceRetrievalStatus,
    _issue_controlled_fetch_transport_authorization,
)
from app.ports.controlled_fetch import (
    ControlledFetchContractViolation,
    ControlledFetchRequestContract,
    ControlledFetchTransportError,
    ControlledHttpFetch,
    FakeControlledHttpTransport,
    TransportResponse,
    bind_url_target,
    fake_resolver_from_fixture,
    validate_url_boundary,
    validate_url_syntax,
)
from app.research.controlled_fetch_intent import (
    CONTROLLED_FETCH_INTENT_VERSION,
    ControlledFetchIntent,
    ControlledFetchIntentError,
    canonicalize_controlled_fetch_payload,
    controlled_fetch_intent_fingerprint,
)
from app.research.evidence import build_evidence_retrieval
NOW = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)
CLOCK = FixedClock(NOW)
PUBLIC_IP = "93.184.216.34"


def _resolver(mapping=None):
    table = {"example.com": (PUBLIC_IP,), **(mapping or {})}

    def resolve(hostname: str):
        resolved = table.get(hostname.lower())
        if resolved is None:
            raise OSError(f"no fake entry for {hostname}")
        return resolved

    return resolve


def make_intent(**overrides) -> ControlledFetchIntent:
    fields = dict(
        account_id="nothing_is_accidental", topic_id=7,
        source_identity="example-doc", requested_url="https://example.com/doc",
        timeout_seconds=10, max_bytes=100_000, max_redirects=2,
        allowed_content_types=["text/html", "text/plain"],
        requested_at=NOW, expires_at=NOW + timedelta(hours=6),
    )
    fields.update(overrides)
    return ControlledFetchIntent.build(**fields)


def make_contract(intent: ControlledFetchIntent) -> ControlledFetchRequestContract:
    return ControlledFetchRequestContract(
        requested_url=intent.requested_url,
        timeout_seconds=intent.timeout_seconds,
        max_bytes=intent.max_bytes,
        max_redirects=intent.max_redirects,
        allowed_content_types=tuple(intent.allowed_content_types),
    )


def make_authorization(intent: ControlledFetchIntent):
    return _issue_controlled_fetch_transport_authorization(
        job_id="job-e2c-unit",
        run_id="run-e2c-unit",
        account_id=intent.account_id,
        topic_id=intent.topic_id,
        approval_id=1,
        attempt_id=1,
        requested_url=intent.requested_url,
        source_identity=intent.source_identity,
        intent_fingerprint=intent.fingerprint,
        timeout_seconds=intent.timeout_seconds,
        max_bytes=intent.max_bytes,
        max_redirects=intent.max_redirects,
        allowed_content_types=tuple(intent.allowed_content_types),
        approval_expires_at=NOW + timedelta(hours=1),
    )


def make_settings(*, real_enabled: bool = False) -> Settings:
    return Settings(
        project_root=Path("."),
        data_dir=Path("."),
        db_path=Path("test.db"),
        costs_csv_path=Path("costs.csv"),
        controlled_fetch_real_enabled=real_enabled,
    )


# --- controlled_fetch_intent_v1 -------------------------------------------------

def test_intent_build_produces_canonical_selfvalidating_fingerprint():
    intent = make_intent()
    assert intent.version == CONTROLLED_FETCH_INTENT_VERSION
    payload = intent.as_payload()
    assert payload["fingerprint"] == controlled_fetch_intent_fingerprint(payload)
    # Round-trip przez JSON nie zmienia tożsamości kontraktu.
    reparsed = ControlledFetchIntent.from_payload(json.loads(json.dumps(payload)))
    assert reparsed == intent


def test_intent_rejects_extra_missing_and_tampered_fields():
    payload = make_intent().as_payload()
    extra = dict(payload, browser="chromium")
    with pytest.raises(ControlledFetchIntentError, match="exactly"):
        ControlledFetchIntent.from_payload(extra)
    missing = dict(payload)
    del missing["max_bytes"]
    with pytest.raises(ControlledFetchIntentError, match="exactly"):
        ControlledFetchIntent.from_payload(missing)
    tampered = dict(payload, requested_url="https://evil.invalid/doc")
    with pytest.raises(ControlledFetchIntentError, match="fingerprint"):
        ControlledFetchIntent.from_payload(tampered)
    forged = dict(tampered)
    forged["fingerprint"] = "0" * 64
    with pytest.raises(ControlledFetchIntentError, match="fingerprint"):
        ControlledFetchIntent.from_payload(forged)


def test_intent_cannot_select_model_provider_browser_or_cost():
    # Zamknięty zbiór pól: każde pole wykonawcze spoza jednego pobrania odpada.
    payload = make_intent().as_payload()
    for hostile in ("model", "provider", "max_cost_usd", "browser", "publish", "module"):
        with pytest.raises(ControlledFetchIntentError, match="exactly"):
            ControlledFetchIntent.from_payload(dict(payload, **{hostile: "x"}))


@pytest.mark.parametrize("field,value", [
    ("timeout_seconds", 0), ("timeout_seconds", 121), ("timeout_seconds", True),
    ("max_bytes", 0), ("max_bytes", 2_000_001),
    ("max_redirects", -1), ("max_redirects", 6),
])
def test_intent_bounds_are_closed(field, value):
    with pytest.raises(ControlledFetchIntentError):
        make_intent(**{field: value})


def test_intent_content_types_are_a_closed_allowlist():
    with pytest.raises(ControlledFetchIntentError, match="allowed_content_types"):
        make_intent(allowed_content_types=["application/pdf"])
    with pytest.raises(ControlledFetchIntentError, match="allowed_content_types"):
        make_intent(allowed_content_types=[])
    with pytest.raises(ControlledFetchIntentError, match="allowed_content_types"):
        make_intent(allowed_content_types=["text/html", "text/html"])


def test_intent_timestamps_must_be_canonical_utc_and_ordered():
    with pytest.raises(ControlledFetchIntentError, match="after requested_at"):
        make_intent(expires_at=NOW)
    payload = make_intent().as_payload()
    drifted = dict(payload, expires_at="2026-07-18 18:00:00")
    with pytest.raises(ControlledFetchIntentError, match="canonical"):
        ControlledFetchIntent.from_payload(drifted)


def test_payload_canonicalization_requires_exact_contract():
    intent = make_intent()
    payload = {
        "account_id": intent.account_id, "topic_id": intent.topic_id,
        "dry_run": False, "execution": "controlled_fetch_v1",
        "execution_intent": intent.as_payload(),
    }
    normalized = canonicalize_controlled_fetch_payload(payload)
    assert normalized["dry_run"] is False
    with pytest.raises(ControlledFetchIntentError, match="dry_run"):
        canonicalize_controlled_fetch_payload(dict(payload, dry_run=True))
    with pytest.raises(ControlledFetchIntentError, match="execution"):
        canonicalize_controlled_fetch_payload(dict(payload, execution="offline_evidence_v1"))
    with pytest.raises(ControlledFetchIntentError, match="identity"):
        canonicalize_controlled_fetch_payload(dict(payload, topic_id=intent.topic_id + 1))
    with pytest.raises(ControlledFetchIntentError, match="exactly"):
        canonicalize_controlled_fetch_payload({**payload, "mode": "single"})


# --- Lokalna polityka adresów ---------------------------------------------------

@pytest.mark.parametrize("url,code", [
    ("ftp://example.com/x", "URL_SCHEME_UNSUPPORTED"),
    ("file:///etc/passwd", "URL_SCHEME_UNSUPPORTED"),
    ("https://user:secret@example.com/", "URL_CREDENTIALS_FORBIDDEN"),
    ("https://user@example.com/", "URL_CREDENTIALS_FORBIDDEN"),
    ("https:///only-path", "URL_HOST_MISSING"),
    ("https://example.com:8080/", "URL_PORT_UNSUPPORTED"),
    ("https://localhost/x", "ADDRESS_LOOPBACK"),
    ("https://api.localhost/x", "ADDRESS_LOOPBACK"),
    ("", "URL_MALFORMED"),
    (" https://example.com/", "URL_MALFORMED"),
])
def test_url_syntax_policy_rejections(url, code):
    decision = validate_url_syntax(url)
    assert not decision.allowed and decision.code == code


@pytest.mark.parametrize("url,code", [
    ("https://127.0.0.1/x", "ADDRESS_LOOPBACK"),
    ("http://[::1]/x", "ADDRESS_LOOPBACK"),
    ("http://10.0.0.5/", "ADDRESS_PRIVATE"),
    ("http://172.16.0.9/", "ADDRESS_PRIVATE"),
    ("http://192.168.1.1/", "ADDRESS_PRIVATE"),
    ("http://169.254.1.1/", "ADDRESS_LINK_LOCAL"),
    ("http://[fe80::1]/", "ADDRESS_LINK_LOCAL"),
    ("http://224.0.0.1/", "ADDRESS_MULTICAST"),
    ("http://0.0.0.0/", "ADDRESS_UNSPECIFIED"),
    ("http://240.0.0.1/", "ADDRESS_RESERVED"),
])
def test_literal_address_boundary_rejections(url, code):
    decision = validate_url_boundary(url, resolver=_resolver())
    assert not decision.allowed and decision.code == code


def test_hostname_boundary_uses_only_the_injected_resolver():
    private = _resolver({"internal.corp": ("10.1.2.3",)})
    rejected = validate_url_boundary("https://internal.corp/x", resolver=private)
    assert rejected.code == "ADDRESS_PRIVATE"
    failed = validate_url_boundary("https://unknown.invalid/x", resolver=_resolver())
    assert failed.code == "DNS_RESOLUTION_FAILED"
    mixed = _resolver({"dual.example": (PUBLIC_IP, "192.168.0.7")})
    assert validate_url_boundary(
        "https://dual.example/x", resolver=mixed,
    ).code == "ADDRESS_PRIVATE"
    allowed = validate_url_boundary("https://example.com/doc", resolver=_resolver())
    assert allowed.allowed and allowed.code == "OK"


def test_fixture_resolver_never_touches_real_dns():
    resolver = fake_resolver_from_fixture(
        {"resolved_addresses": {"example.com": [PUBLIC_IP]}}
    )
    assert resolver("EXAMPLE.com") == (PUBLIC_IP,)
    with pytest.raises(OSError):
        resolver("other.invalid")


# --- Fake transport i adapter ---------------------------------------------------

def _adapter(intent, transport, resolver=None):
    return ControlledHttpFetch(
        contract=make_contract(intent), transport=transport,
        resolver=resolver or _resolver(), clock=CLOCK,
    )


def _html(status=200, body="<html><body><p>Durable fetched evidence body.</p></body></html>",
          content_type="text/html; charset=utf-8", location=None):
    return TransportResponse(
        status=status, content_type=content_type, location=location,
        body=body.encode("utf-8"), body_complete=True,
    )


def test_adapter_success_produces_typed_document_and_ok_retrieval():
    intent = make_intent()
    transport = FakeControlledHttpTransport({intent.requested_url: _html()})
    document = _adapter(intent, transport).fetch(intent.requested_url)
    assert document.error is None and document.http_status == 200
    assert document.final_url == intent.requested_url
    assert transport.calls[0]["timeout_seconds"] == intent.timeout_seconds
    assert transport.calls[0]["max_read_bytes"] == intent.max_bytes
    retrieval = build_evidence_retrieval(document, account_id=intent.account_id, now=NOW)
    assert retrieval.status is EvidenceRetrievalStatus.OK
    assert "Durable fetched evidence body." in retrieval.canonical_text


def test_adapter_follows_redirects_within_budget_and_policy():
    intent = make_intent()
    final = "https://example.com/final"
    transport = FakeControlledHttpTransport({
        intent.requested_url: _html(status=302, location="/final", body=""),
        final: _html(),
    })
    document = _adapter(intent, transport).fetch(intent.requested_url)
    assert document.error is None
    assert document.final_url == final
    assert document.requested_url == intent.requested_url


def test_adapter_rejects_redirect_over_budget():
    intent = make_intent(max_redirects=0)
    transport = FakeControlledHttpTransport({
        intent.requested_url: _html(status=301, location="/next", body=""),
    })
    document = _adapter(intent, transport).fetch(intent.requested_url)
    assert document.error == "TOO_MANY_REDIRECTS"


def test_adapter_rejects_redirect_crossing_the_address_boundary():
    intent = make_intent()
    transport = FakeControlledHttpTransport({
        intent.requested_url: _html(status=302, location="http://10.0.0.7/steal", body=""),
    })
    document = _adapter(intent, transport).fetch(intent.requested_url)
    assert document.error == "REDIRECT_POLICY_REJECTED:ADDRESS_PRIVATE"


def test_adapter_enforces_hard_byte_cap():
    intent = make_intent(max_bytes=64)
    transport = FakeControlledHttpTransport({
        intent.requested_url: _html(body="x" * 200),
    })
    document = _adapter(intent, transport).fetch(intent.requested_url)
    assert document.error == "RESPONSE_TOO_LARGE"


def test_adapter_rejects_unsupported_content_type():
    intent = make_intent()
    transport = FakeControlledHttpTransport({
        intent.requested_url: _html(content_type="application/json"),
    })
    document = _adapter(intent, transport).fetch(intent.requested_url)
    assert document.error == "CONTENT_TYPE_REJECTED:application/json"


def test_adapter_converts_typed_transport_error_to_typed_document():
    intent = make_intent()
    document = _adapter(intent, FakeControlledHttpTransport()).fetch(intent.requested_url)
    assert document.error == "FAKE_URL_NOT_REGISTERED"
    assert document.body == b""


def test_adapter_refuses_any_url_outside_the_frozen_contract():
    intent = make_intent()
    adapter = _adapter(intent, FakeControlledHttpTransport())
    with pytest.raises(ControlledFetchContractViolation):
        adapter.fetch("https://example.com/other")


def test_adapter_returns_non_2xx_as_definitive_failed_classification():
    intent = make_intent()
    transport = FakeControlledHttpTransport({
        intent.requested_url: _html(status=503),
    })
    document = _adapter(intent, transport).fetch(intent.requested_url)
    assert document.error is None and document.http_status == 503
    retrieval = build_evidence_retrieval(document, account_id=intent.account_id, now=NOW)
    assert retrieval.status is EvidenceRetrievalStatus.FAILED
    assert retrieval.fetch_error == "HTTP_STATUS_503"


def test_adapter_preflight_boundary_rejects_before_any_transport_call():
    intent = make_intent(requested_url="https://blocked.internal/doc")
    transport = FakeControlledHttpTransport()
    adapter = ControlledHttpFetch(
        contract=make_contract(intent), transport=transport,
        resolver=_resolver({"blocked.internal": ("127.0.0.1",)}), clock=CLOCK,
    )
    decision = adapter.preflight_boundary()
    assert not decision.allowed and decision.code == "ADDRESS_LOOPBACK"
    assert transport.calls == []


def test_fake_transport_never_returns_more_than_the_cap():
    transport = FakeControlledHttpTransport({"https://example.com/doc": _html(body="y" * 100)})
    binding = bind_url_target(
        "https://example.com/doc",
        resolver=_resolver(),
    )
    assert binding.target is not None
    response = transport.request(
        binding.target,
        timeout_seconds=5,
        max_read_bytes=10,
    )
    assert len(response.body) == 10 and response.body_complete is False


def test_transport_error_carries_controlled_code_only():
    error = ControlledFetchTransportError("TIMEOUT")
    assert error.code == "TIMEOUT" and str(error) == "TIMEOUT"


# --- Composition gate -----------------------------------------------------------

def test_real_controlled_fetch_is_globally_disabled_by_default():
    assert make_settings().controlled_fetch_real_enabled is False


def test_composition_gate_fails_closed_without_fake_fixture(monkeypatch):
    from app.workflows.research.controlled_fetch import (
        ControlledFetchUnavailableError,
        resolve_controlled_fetch_port,
    )

    authorization = make_authorization(make_intent())
    monkeypatch.delenv("NIA_CONTROLLED_FETCH_FAKE", raising=False)
    monkeypatch.delenv("NIA_CONTROLLED_FETCH_FIXTURE", raising=False)
    with pytest.raises(ControlledFetchUnavailableError, match="globally disabled"):
        resolve_controlled_fetch_port(
            authorization,
            settings=make_settings(),
            clock=CLOCK,
        )

    monkeypatch.setenv("NIA_CONTROLLED_FETCH_FAKE", "1")
    with pytest.raises(ControlledFetchUnavailableError, match="fixture"):
        resolve_controlled_fetch_port(
            authorization,
            settings=make_settings(),
            clock=CLOCK,
        )

    monkeypatch.delenv("NIA_TEST_MODE", raising=False)
    with pytest.raises(ControlledFetchUnavailableError, match="NIA_TEST_MODE"):
        resolve_controlled_fetch_port(
            authorization,
            settings=make_settings(),
            clock=CLOCK,
        )


def test_composition_gate_builds_fake_port_from_explicit_fixture(tmp_path, monkeypatch):
    from app.workflows.research.controlled_fetch import resolve_controlled_fetch_port

    intent = make_intent()
    fixture = tmp_path / "fetch-fixture.json"
    fixture.write_text(json.dumps({
        "responses": {intent.requested_url: {
            "status": 200, "content_type": "text/html; charset=utf-8",
            "body_utf8": "<p>Fixture body for the controlled fetch gate.</p>",
        }},
        "resolved_addresses": {"example.com": [PUBLIC_IP]},
    }), encoding="utf-8")
    monkeypatch.setenv("NIA_CONTROLLED_FETCH_FAKE", "1")
    monkeypatch.setenv("NIA_CONTROLLED_FETCH_FIXTURE", str(fixture))
    port = resolve_controlled_fetch_port(
        make_authorization(intent),
        settings=make_settings(),
        clock=CLOCK,
    )
    assert isinstance(port, ControlledHttpFetch)
    document = port.fetch(intent.requested_url)
    assert document.error is None and document.http_status == 200

"""LA-01-A: authoritative versioned pricing profile contract (offline, temp files)."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from app.core.money import sum_usd
from app.core.pricing import (
    PricingConfigError,
    assert_frozen_pricing_contract,
    load_pricing_profiles,
    resolve_real_pricing_profile,
)
from app.research.cost_estimator import estimate_worst_case_search_call_usd
from app.research.durable_intent import DurableResearchExecutionIntent

from tests.conftest import write_approved_pricing_profile

MODEL = "dry-run-fake"
_PRICES = {
    "input_per_mtok": 3.0, "output_per_mtok": 15.0, "cache_read_per_mtok": 0.3,
    "cache_write_per_mtok": 3.75, "web_search_per_1k": 10.0,
}


def _write(tmp_path: Path, profiles: list[dict]) -> Path:
    path = tmp_path / "pricing_profiles.yaml"
    path.write_text(yaml.safe_dump({"version": 1, "profiles": profiles}), encoding="utf-8")
    return path


def _profile(**overrides) -> dict:
    base = {
        "profile_id": "p-approved", "version": "2026-01-01", "model": MODEL,
        "currency": "USD", "unit": "usd_per_mtok__web_search_per_1k",
        "status": "approved", "approved_by": "owner", "prices": dict(_PRICES),
    }
    base.update(overrides)
    return base


# 1. example profile blocks real execution
def test_example_profile_blocks_real_execution(tmp_path):
    path = _write(tmp_path, [_profile(status="example")])
    profiles = load_pricing_profiles(path)
    with pytest.raises(PricingConfigError, match="status"):
        resolve_real_pricing_profile(profiles, profile_id="p-approved", model=MODEL)


# 2. missing profile id blocks
def test_missing_profile_blocks(tmp_path):
    path = _write(tmp_path, [_profile()])
    profiles = load_pricing_profiles(path)
    with pytest.raises(PricingConfigError, match="Brak aktywnego profilu"):
        resolve_real_pricing_profile(profiles, profile_id="does-not-exist", model=MODEL)
    with pytest.raises(PricingConfigError):
        resolve_real_pricing_profile(profiles, profile_id="", model=MODEL)


# 3. incomplete / non-positive profile blocks
def test_incomplete_or_nonpositive_profile_blocks(tmp_path):
    # missing a required price key is rejected at load time
    bad = _profile()
    del bad["prices"]["web_search_per_1k"]
    missing_path = tmp_path / "missing.yaml"
    missing_path.write_text(yaml.safe_dump({"version": 1, "profiles": [bad]}), encoding="utf-8")
    with pytest.raises(PricingConfigError, match="dokładnie klucze"):
        load_pricing_profiles(missing_path)
    # zero / negative prices are rejected at resolution
    for index, value in enumerate((0.0, -1.0)):
        prices = dict(_PRICES); prices["output_per_mtok"] = value
        path = tmp_path / f"nonpositive_{index}.yaml"
        path.write_text(yaml.safe_dump({"version": 1, "profiles": [_profile(prices=prices)]}), encoding="utf-8")
        profiles = load_pricing_profiles(path)
        with pytest.raises(PricingConfigError, match="niepełne, zerowe albo ujemne"):
            resolve_real_pricing_profile(profiles, profile_id="p-approved", model=MODEL)


# 4. model mismatch blocks
def test_model_mismatch_blocks(tmp_path):
    path = _write(tmp_path, [_profile(model="some-other-model")])
    profiles = load_pricing_profiles(path)
    with pytest.raises(PricingConfigError, match="Model musi pasować"):
        resolve_real_pricing_profile(profiles, profile_id="p-approved", model=MODEL)


# 5. approved, versioned, model-matched profile passes
def test_approved_profile_passes(tmp_path):
    path = _write(tmp_path, [_profile()])
    profiles = load_pricing_profiles(path)
    resolved = resolve_real_pricing_profile(profiles, profile_id="p-approved", model=MODEL)
    assert resolved.is_approved
    assert resolved.version == "2026-01-01"
    assert resolved.model == MODEL
    assert all(isinstance(value, Decimal) for value in resolved.prices.values())


# 5b. no-version profile blocks
def test_unversioned_profile_blocks(tmp_path):
    p = tmp_path / "nv.yaml"
    p.write_text(yaml.safe_dump({"version": 1, "profiles": [_profile(version="")]}), encoding="utf-8")
    profiles = load_pricing_profiles(p)
    with pytest.raises(PricingConfigError, match="wersj"):
        resolve_real_pricing_profile(profiles, profile_id="p-approved", model=MODEL)


# 5c. approved_by is mandatory and whitespace does not count as approval
@pytest.mark.parametrize("approved_by", [None, "", "   "])
def test_approved_profile_without_named_approver_blocks(tmp_path, approved_by):
    raw = _profile()
    if approved_by is None:
        raw.pop("approved_by")
    else:
        raw["approved_by"] = approved_by
    profiles = load_pricing_profiles(_write(tmp_path, [raw]))
    with pytest.raises(PricingConfigError, match="approved_by"):
        resolve_real_pricing_profile(
            profiles,
            profile_id="p-approved",
            model=MODEL,
        )


# 6. fingerprint is stable and persisted in the durable intent
def test_pricing_fingerprint_is_stable_and_persisted(tmp_path, settings, account):
    path = _write(tmp_path, [_profile()])
    profile = resolve_real_pricing_profile(load_pricing_profiles(path), profile_id="p-approved", model=MODEL)
    assert profile.fingerprint() == profile.fingerprint()
    real = replace(settings, model_quality=MODEL)
    intent = DurableResearchExecutionIntent.from_settings(
        settings=real, account_id=account.id, topic_id=1, cap_usd=0.5, max_web_searches=2,
        question="Why?", niche=account.niche, max_tokens=1000,
        pricing_prices=profile.prices, pricing_profile_id=profile.profile_id,
        pricing_profile_version=profile.version,
    )
    payload = intent.as_payload()
    assert payload["pricing_profile_id"] == "p-approved"
    assert payload["pricing_profile_version"] == "2026-01-01"
    assert payload["pricing_fingerprint"] == intent.pricing_fingerprint
    # round-trips without loss
    again = DurableResearchExecutionIntent.from_payload(payload)
    assert again.pricing_fingerprint == intent.pricing_fingerprint
    assert again.pricing_profile_id == "p-approved"


# 6b. every frozen pricing field participates in authorization
@pytest.mark.parametrize(
    "forgery",
    ["profile_id", "version", "model", "prices", "fingerprint"],
)
def test_forged_frozen_pricing_contract_blocks(tmp_path, forgery):
    profile = resolve_real_pricing_profile(
        load_pricing_profiles(_write(tmp_path, [_profile()])),
        profile_id="p-approved",
        model=MODEL,
    )
    frozen = {
        "profile_id": profile.profile_id,
        "version": profile.version,
        "model": profile.model,
        "currency": profile.currency,
        "unit": profile.unit,
        "prices": dict(profile.prices),
        "fingerprint": profile.fingerprint(),
    }
    if forgery == "prices":
        frozen["prices"]["output_per_mtok"] = Decimal("99")
    elif forgery == "fingerprint":
        frozen["fingerprint"] = "0" * 64
    else:
        frozen[forgery] = f"forged-{forgery}"
    with pytest.raises(PricingConfigError, match="Frozen pricing"):
        assert_frozen_pricing_contract(profile=profile, **frozen)


# 7. changing the pricing file after enqueue does not change the persisted contract
def test_pricing_file_change_after_enqueue_does_not_change_persisted_contract(tmp_path, settings, account):
    path = _write(tmp_path, [_profile()])
    profile = resolve_real_pricing_profile(load_pricing_profiles(path), profile_id="p-approved", model=MODEL)
    real = replace(settings, model_quality=MODEL)
    intent = DurableResearchExecutionIntent.from_settings(
        settings=real, account_id=account.id, topic_id=1, cap_usd=0.5, max_web_searches=2,
        question="Why?", niche=account.niche, max_tokens=1000,
        pricing_prices=profile.prices, pricing_profile_id=profile.profile_id,
        pricing_profile_version=profile.version,
    )
    persisted = intent.as_payload()
    # Operator edits the file afterwards (doubles every price, bumps version).
    edited = _profile(version="2099-12-31", prices={k: v * 2 for k, v in _PRICES.items()})
    _write(tmp_path, [edited])
    # The already-persisted payload is unaffected.
    assert persisted["pricing_profile"]["output_per_mtok"] == "15.000000"
    assert persisted["pricing_profile_version"] == "2026-01-01"
    reloaded = DurableResearchExecutionIntent.from_payload(persisted)
    assert reloaded.runtime_pricing()["output_per_mtok"] == 15.0
    current = resolve_real_pricing_profile(
        load_pricing_profiles(path),
        profile_id="p-approved",
        model=MODEL,
    )
    with pytest.raises(PricingConfigError, match="Frozen pricing"):
        assert_frozen_pricing_contract(
            profile=current,
            profile_id=reloaded.pricing_profile_id,
            version=reloaded.pricing_profile_version,
            model=reloaded.model,
            currency=reloaded.pricing_currency,
            unit=reloaded.pricing_unit,
            prices=reloaded.pricing_profile,
            fingerprint=reloaded.pricing_fingerprint,
        )


# 8. projected cost uses exactly the persisted prices, not ambient settings pricing
def test_projected_cost_uses_persisted_prices(tmp_path, settings, account):
    path = _write(tmp_path, [_profile()])
    profile = resolve_real_pricing_profile(load_pricing_profiles(path), profile_id="p-approved", model=MODEL)
    real = replace(settings, model_quality=MODEL, pricing={k: 999.0 for k in _PRICES})
    intent = DurableResearchExecutionIntent.from_settings(
        settings=real, account_id=account.id, topic_id=1, cap_usd=0.5, max_web_searches=2,
        question="Why?", niche=account.niche, max_tokens=1000,
        pricing_prices=profile.prices, pricing_profile_id=profile.profile_id,
        pricing_profile_version=profile.version,
    )
    # The persisted profile wins over the (deliberately absurd) ambient settings pricing.
    assert intent.runtime_pricing() == {k: float(v) for k, v in _PRICES.items()}
    priced = replace(real, pricing=intent.runtime_pricing())
    est = estimate_worst_case_search_call_usd(priced, max_web_searches=2, max_output_tokens=1000)
    absurd = estimate_worst_case_search_call_usd(real, max_web_searches=2, max_output_tokens=1000)
    assert est.total_usd < absurd.total_usd


# 9. money stays Decimal to the final boundary (no float drift in persisted prices)
def test_prices_are_decimal_canonicalized(tmp_path, settings, account):
    prices = dict(_PRICES); prices["input_per_mtok"] = 3.1234567  # 7 dp -> canonical 6 dp
    p = tmp_path / "d.yaml"
    p.write_text(yaml.safe_dump({"version": 1, "profiles": [_profile(prices=prices)]}), encoding="utf-8")
    profile = resolve_real_pricing_profile(load_pricing_profiles(p), profile_id="p-approved", model=MODEL)
    real = replace(settings, model_quality=MODEL)
    intent = DurableResearchExecutionIntent.from_settings(
        settings=real, account_id=account.id, topic_id=1, cap_usd=0.5, max_web_searches=1,
        question="Why?", niche=account.niche, max_tokens=1000,
        pricing_prices=profile.prices, pricing_profile_id=profile.profile_id,
        pricing_profile_version=profile.version,
    )
    assert intent.as_payload()["pricing_profile"]["input_per_mtok"] == "3.123457"


# 10. three half-quantum components round once at the shared boundary
def test_three_half_quantum_components_round_once():
    total = sum_usd((Decimal("0.0000005"), Decimal("0.0000005"), Decimal("0.0000005")), label="half-quanta")
    assert total == Decimal("0.000002")

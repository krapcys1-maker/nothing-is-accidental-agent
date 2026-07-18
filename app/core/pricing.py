"""Autorytatywne, wersjonowane profile cenowe realnego paid flow.

`.env` nie jest źródłem realnego cennika. Operator zatwierdza konkretny profil
w `config/pricing_profiles.yaml`; wartości są parsowane jako ``Decimal`` i
zamrażane razem z pełną tożsamością profilu.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
from typing import Mapping

import yaml

from app.core.config import REAL_PROVIDER_PRICING_KEYS, ConfigError

STATUS_EXAMPLE = "example"
STATUS_APPROVED = "approved"
_ALLOWED_STATUS = (STATUS_EXAMPLE, STATUS_APPROVED)
REQUIRED_CURRENCY = "USD"
REQUIRED_UNIT = "usd_per_mtok__web_search_per_1k"
_USD_QUANTUM = Decimal("0.000001")


class PricingConfigError(ConfigError):
    """The authoritative pricing configuration is missing, malformed or unapproved."""


def canonical_price(value: object, *, field: str) -> str:
    """Return a six-decimal representation without a float round-trip."""
    if isinstance(value, bool):
        raise PricingConfigError(f"{field} must be a decimal amount, not bool.")
    try:
        amount = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PricingConfigError(f"{field} must be a finite decimal amount.") from exc
    if not amount.is_finite():
        raise PricingConfigError(f"{field} must be a finite decimal amount.")
    return format(amount.quantize(_USD_QUANTUM), ".6f")


def pricing_contract_fingerprint(
    *,
    profile_id: object,
    version: object,
    model: object,
    currency: object,
    unit: object,
    prices: Mapping[str, object],
) -> str:
    """Hash identity, version, model, units and every canonical price."""
    if set(prices) != set(REAL_PROVIDER_PRICING_KEYS):
        raise PricingConfigError(
            "pricing contract must contain exactly the real-provider price keys."
        )
    canonical = json.dumps(
        {
            "profile_id": str(profile_id),
            "version": str(version),
            "model": str(model),
            "currency": str(currency),
            "unit": str(unit),
            "prices": {
                key: canonical_price(prices[key], field=f"prices.{key}")
                for key in REAL_PROVIDER_PRICING_KEYS
            },
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PricingProfile:
    profile_id: str
    version: str
    model: str
    currency: str
    unit: str
    status: str
    approved_by: str
    approved_at: str | None
    prices: Mapping[str, Decimal]

    @property
    def is_approved(self) -> bool:
        return self.status == STATUS_APPROVED

    def fingerprint(self) -> str:
        return pricing_contract_fingerprint(
            profile_id=self.profile_id,
            version=self.version,
            model=self.model,
            currency=self.currency,
            unit=self.unit,
            prices=self.prices,
        )


def default_pricing_profiles_path(project_root: Path) -> Path:
    """Resolve an explicit test override, the approved file, or example fallback."""
    override = os.getenv("NIA_PRICING_PROFILES_PATH")
    if override:
        return Path(override)
    config_dir = project_root / "config"
    real = config_dir / "pricing_profiles.yaml"
    if real.exists():
        return real
    return config_dir / "pricing_profiles.example.yaml"


def _required_text(raw: Mapping[object, object], key: str, *, profile_id: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PricingConfigError(f"Profil {profile_id!r} wymaga niepustego {key}.")
    return value.strip()


def _price_value(raw: object, *, profile_id: str, key: str) -> Decimal:
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str, Decimal)):
        raise PricingConfigError(
            f"Profil {profile_id!r}: cena {key!r} musi być liczbą dziesiętną."
        )
    try:
        value = raw if isinstance(raw, Decimal) else Decimal(str(raw))
    except (InvalidOperation, ValueError) as exc:
        raise PricingConfigError(
            f"Profil {profile_id!r}: cena {key!r} nie jest liczbą dziesiętną."
        ) from exc
    if not value.is_finite():
        raise PricingConfigError(f"Profil {profile_id!r}: cena {key!r} nie jest skończona.")
    return value


def _parse_profile(raw: object) -> PricingProfile:
    if not isinstance(raw, Mapping):
        raise PricingConfigError("Każdy profil cenowy musi być mapą pól.")
    profile_id_raw = raw.get("profile_id")
    if not isinstance(profile_id_raw, str) or not profile_id_raw.strip():
        raise PricingConfigError("Profil cenowy wymaga niepustego profile_id.")
    profile_id = profile_id_raw.strip()

    version_raw = raw.get("version")
    version = "" if version_raw is None else str(version_raw).strip()
    model = _required_text(raw, "model", profile_id=profile_id)
    currency = _required_text(raw, "currency", profile_id=profile_id)
    unit = _required_text(raw, "unit", profile_id=profile_id)

    status = raw.get("status")
    if status not in _ALLOWED_STATUS:
        raise PricingConfigError(
            f"Profil {profile_id!r}: status musi być jednym z {_ALLOWED_STATUS}."
        )
    approved_by_raw = raw.get("approved_by")
    if approved_by_raw is None:
        approved_by = ""
    elif not isinstance(approved_by_raw, str):
        raise PricingConfigError(f"Profil {profile_id!r}: approved_by musi być tekstem.")
    else:
        approved_by = approved_by_raw.strip()
    approved_at_raw = raw.get("approved_at")
    if approved_at_raw is None:
        approved_at = None
    elif not isinstance(approved_at_raw, str) or not approved_at_raw.strip():
        raise PricingConfigError(
            f"Profil {profile_id!r}: approved_at musi być niepustym tekstem ISO."
        )
    else:
        approved_at = approved_at_raw.strip()

    prices_raw = raw.get("prices")
    if not isinstance(prices_raw, Mapping):
        raise PricingConfigError(f"Profil {profile_id!r}: prices musi być mapą cen.")
    if set(prices_raw) != set(REAL_PROVIDER_PRICING_KEYS):
        raise PricingConfigError(
            f"Profil {profile_id!r}: prices musi mieć dokładnie klucze "
            f"{REAL_PROVIDER_PRICING_KEYS}."
        )
    prices = {
        key: _price_value(prices_raw[key], profile_id=profile_id, key=key)
        for key in REAL_PROVIDER_PRICING_KEYS
    }
    return PricingProfile(
        profile_id=profile_id,
        version=version,
        model=model,
        currency=currency,
        unit=unit,
        status=str(status),
        approved_by=approved_by,
        approved_at=approved_at,
        prices=prices,
    )


def load_pricing_profiles(path: Path) -> tuple[PricingProfile, ...]:
    if not path.exists():
        raise PricingConfigError(
            f"Brak autorytatywnego pliku cennika: {path}. "
            "Realne wykonanie wymaga zatwierdzonego profilu."
        )
    with path.open("r", encoding="utf-8") as handle:
        document = yaml.safe_load(handle) or {}
    if not isinstance(document, Mapping):
        raise PricingConfigError("Plik cennika musi być mapą z listą 'profiles'.")
    raw_profiles = document.get("profiles")
    if not isinstance(raw_profiles, list) or not raw_profiles:
        raise PricingConfigError("Plik cennika musi zawierać niepustą listę 'profiles'.")
    profiles = tuple(_parse_profile(item) for item in raw_profiles)
    seen: set[str] = set()
    for profile in profiles:
        if profile.profile_id in seen:
            raise PricingConfigError(f"Zduplikowany profile_id: {profile.profile_id!r}.")
        seen.add(profile.profile_id)
    return profiles


def resolve_real_pricing_profile(
    profiles: tuple[PricingProfile, ...], *, profile_id: str, model: str,
) -> PricingProfile:
    """Return the one profile that authorizes a real request, or fail closed."""
    if not isinstance(profile_id, str) or not profile_id.strip():
        raise PricingConfigError(
            "Realne wykonanie wymaga jawnego --pricing-profile."
        )
    profile_id = profile_id.strip()
    match = next((profile for profile in profiles if profile.profile_id == profile_id), None)
    if match is None:
        raise PricingConfigError(
            f"Brak aktywnego profilu cenowego o id={profile_id!r}."
        )
    if match.status != STATUS_APPROVED:
        raise PricingConfigError(
            f"Profil {profile_id!r} ma status {match.status!r}; wymagany jest approved."
        )
    if not match.version:
        raise PricingConfigError(
            f"Profil {profile_id!r} nie ma zatwierdzonego identyfikatora wersji."
        )
    if not match.approved_by:
        raise PricingConfigError(
            f"Profil {profile_id!r} ma status approved, ale nie ma approved_by."
        )
    if match.currency != REQUIRED_CURRENCY:
        raise PricingConfigError(
            f"Profil {profile_id!r}: waluta {match.currency!r} != {REQUIRED_CURRENCY!r}."
        )
    if match.unit != REQUIRED_UNIT:
        raise PricingConfigError(
            f"Profil {profile_id!r}: jednostka {match.unit!r} != {REQUIRED_UNIT!r}."
        )
    if match.model != model:
        raise PricingConfigError(
            f"Profil {profile_id!r} dotyczy modelu {match.model!r}, a żądanie używa "
            f"{model!r}. Model musi pasować do zatwierdzonego profilu."
        )
    invalid = [
        key
        for key in REAL_PROVIDER_PRICING_KEYS
        if key not in match.prices
        or not isinstance(match.prices[key], Decimal)
        or not match.prices[key].is_finite()
        or match.prices[key] <= 0
    ]
    if invalid:
        raise PricingConfigError(
            f"Profil {profile_id!r}: ceny {invalid} są niepełne, zerowe albo ujemne."
        )
    return match


def assert_frozen_pricing_contract(
    *,
    profile: PricingProfile,
    profile_id: str,
    version: str,
    model: str,
    currency: str,
    unit: str,
    prices: Mapping[str, object],
    fingerprint: str,
) -> None:
    """Compare every frozen field with the currently approved profile."""
    expected_prices = {
        key: canonical_price(profile.prices[key], field=f"approved.{key}")
        for key in REAL_PROVIDER_PRICING_KEYS
    }
    actual_prices = {
        key: canonical_price(prices[key], field=f"frozen.{key}")
        for key in REAL_PROVIDER_PRICING_KEYS
    }
    if (
        profile.profile_id != profile_id
        or profile.version != version
        or profile.model != model
        or profile.currency != currency
        or profile.unit != unit
        or expected_prices != actual_prices
        or profile.fingerprint() != fingerprint
    ):
        raise PricingConfigError(
            "Frozen pricing contract differs from the approved profile."
        )

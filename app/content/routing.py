"""Versioned routing that never confuses a logical route with an API model."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.content.contracts import RouteContract
from app.content.foundation import ContentType, canonical_json, sha256_text


class ContentRoutingError(RuntimeError):
    pass


class RealContentWriterUnavailable(ContentRoutingError):
    """The supported C3 composition roots do not authorize a real call."""


class MissingContentWriterConfiguration(RealContentWriterUnavailable):
    pass


class MissingContentWriterPricing(RealContentWriterUnavailable):
    pass


class ContentWriterProviderUnavailable(RealContentWriterUnavailable):
    pass


@dataclass(frozen=True)
class ResolvedWriterRoute:
    content_type: ContentType
    logical_route_key: str
    provider: str
    api_model_id: str
    pricing_profile: str
    configuration_status: str
    fallback: str


def default_content_routing_path(project_root: Path) -> Path:
    return project_root / "config" / "content_routing.yaml"


def load_content_route(path: Path, content_type: ContentType) -> RouteContract:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ContentRoutingError("Versioned content routing configuration is unavailable.") from exc
    if not isinstance(raw, dict) or set(raw) != {"version", "mode", "fallback", "routes"}:
        raise ContentRoutingError("Content routing document has an unsupported shape.")
    if raw["mode"] not in {"FAKE_ONLY", "PROVIDER_READY"}:
        raise ContentRoutingError("Content routing mode is unsupported.")
    if raw["fallback"] != "FORBIDDEN":
        raise ContentRoutingError("Content routing fallback must be FORBIDDEN.")
    routes = raw["routes"]
    if not isinstance(routes, dict) or set(routes) != {"ARTICLE", "NOTE"}:
        raise ContentRoutingError("Content routing must define exactly ARTICLE and NOTE.")
    selected = routes.get(content_type.value)
    if not isinstance(selected, dict):
        raise ContentRoutingError(f"Missing route for {content_type.value}.")
    required = {
        "route_key", "logical_model_name", "provider", "api_model_id",
        "availability", "pricing_profile",
    }
    if set(selected) != required:
        raise ContentRoutingError("Selected route has an unsupported field set.")
    fingerprint = sha256_text(canonical_json(raw))
    return RouteContract(
        content_type=content_type,
        route_key=selected["route_key"],
        logical_model_name=selected["logical_model_name"],
        config_version=raw["version"],
        config_fingerprint=fingerprint,
        provider=selected["provider"],
        api_model_id=selected["api_model_id"],
        availability=selected["availability"],
        pricing_profile=selected["pricing_profile"],
        fallback=raw["fallback"],
    )


def resolve_provider_route(route: RouteContract) -> ResolvedWriterRoute:
    """Resolve a complete technical route or fail before any client exists."""
    if route.provider == "UNVERIFIED" or route.api_model_id == "UNVERIFIED":
        raise MissingContentWriterConfiguration(
            "Provider and technical API model ID must be explicitly configured."
        )
    if route.pricing_profile == "UNVERIFIED":
        raise MissingContentWriterPricing(
            "Writer pricing profile must be explicitly configured."
        )
    if route.availability != "CONFIGURED":
        raise ContentWriterProviderUnavailable(
            "Writer provider is not configured as available for this runtime."
        )
    if route.configuration_status != "CONFIGURED":
        raise MissingContentWriterConfiguration(
            "Writer route configuration is incomplete."
        )
    return ResolvedWriterRoute(
        content_type=route.content_type,
        logical_route_key=route.route_key,
        provider=route.provider,
        api_model_id=route.api_model_id,
        pricing_profile=route.pricing_profile,
        configuration_status=route.configuration_status,
        fallback=route.fallback,
    )


def resolve_real_content_writer(_route: RouteContract) -> Any:
    resolve_provider_route(_route)
    raise RealContentWriterUnavailable(
        "C3 provides an adapter boundary but no supported real-provider "
        "composition root. Controlled-live belongs to C5."
    )

"""Versioned, fail-closed logical routing for the offline C2 writer."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.content.contracts import RouteContract
from app.content.foundation import ContentType, canonical_json, sha256_text


class ContentRoutingError(RuntimeError):
    pass


class RealContentWriterUnavailable(ContentRoutingError):
    """C2 intentionally has no reachable real provider composition root."""


def default_content_routing_path(project_root: Path) -> Path:
    return project_root / "config" / "content_routing.yaml"


def load_content_route(path: Path, content_type: ContentType) -> RouteContract:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ContentRoutingError("Versioned content routing configuration is unavailable.") from exc
    if not isinstance(raw, dict) or set(raw) != {"version", "mode", "fallback", "routes"}:
        raise ContentRoutingError("Content routing document has an unsupported shape.")
    if raw["mode"] != "FAKE_ONLY" or raw["fallback"] != "FORBIDDEN":
        raise ContentRoutingError("C2 routing must be FAKE_ONLY with fallback FORBIDDEN.")
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


def resolve_real_content_writer(_route: RouteContract) -> Any:
    raise RealContentWriterUnavailable(
        "Real content writer is unreachable in C2: provider, API model ID, "
        "availability and pricing are UNVERIFIED."
    )

"""Production ARTICLE_RESEARCH A1 connector.

Only structured ``web_search_result`` tool blocks become candidates.  Model
free text is deliberately ignored and therefore can never authorize a URL.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

from app.llm.base import Usage
from app.ports.source_discovery import (
    SourceDiscoveryCandidate,
    SourceDiscoveryRequest,
    SourceDiscoveryResponse,
)


_UNFETCHABLE_HOST_SUFFIXES = (
    "academia.edu",
    "sciencedirect.com",
    "tandfonline.com",
)


def _value(item: object, name: str, default: object = None) -> object:
    return item.get(name, default) if isinstance(item, dict) else getattr(item, name, default)


def canonical_source_identity(url: str) -> tuple[str, str]:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if not host or parts.scheme.lower() not in {"http", "https"}:
        raise ValueError("structured search result URL is not canonicalizable")
    port = parts.port
    netloc = host if port is None else f"{host}:{port}"
    canonical = urlunsplit((parts.scheme.lower(), netloc, parts.path or "/", parts.query, ""))
    identity = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return canonical, f"url-sha256:{identity}"


def is_controlled_fetch_candidate(url: str) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    path = parts.path.lower()
    if any(host == suffix or host.endswith(f".{suffix}") for suffix in _UNFETCHABLE_HOST_SUFFIXES):
        return False
    return not (path.endswith(".pdf") or "/pdf/" in path)


class AnthropicSourceDiscoveryPort:
    def __init__(self, *, api_key: str, model: str, sdk_factory: Callable[[str], object],
                 now: Callable[[], datetime] | None = None) -> None:
        self._api_key = api_key
        self._model = model
        self._sdk_factory = sdk_factory
        self._now = now or (lambda: datetime.now(timezone.utc))

    def discover(self, request: SourceDiscoveryRequest) -> SourceDiscoveryResponse:
        client = self._sdk_factory(self._api_key)
        response = client.messages.create(
            model=self._model,
            max_tokens=8192,
            inference_geo="global",
            service_tier="standard_only",
            tools=[{
                "type": "web_search_20250305", "name": "web_search",
                "max_uses": request.max_results,
            }],
            messages=[{"role": "user", "content": (
                f"Find exactly {request.max_results} authoritative sources for this "
                "research question. Every source must be publicly fetchable without "
                "login or subscription and must be an HTML or plain-text page, never a "
                "PDF. Prefer government, transit-agency, university, standards-body, "
                "and other primary public pages. Never return sciencedirect.com, "
                "tandfonline.com, or academia.edu. Use no more than the available search "
                "calls. Source selection only; do not synthesize claims.\n" + request.query
            )}],
        )
        provider_request_id = str(_value(response, "id", ""))
        if not provider_request_id:
            raise ValueError("source-discovery response lacks provider request identity")
        observed_at = self._now().astimezone(timezone.utc).isoformat()
        candidates: list[SourceDiscoveryCandidate] = []
        for block in tuple(_value(response, "content", ()) or ()):
            if _value(block, "type") != "web_search_tool_result":
                continue
            for result in tuple(_value(block, "content", ()) or ()):
                if _value(result, "type") != "web_search_result":
                    continue
                raw_url = _value(result, "url")
                raw_title = _value(result, "title")
                if not isinstance(raw_url, str) or not isinstance(raw_title, str):
                    continue
                canonical_url, source_identity = canonical_source_identity(raw_url)
                if not is_controlled_fetch_candidate(canonical_url):
                    continue
                result_identity = hashlib.sha256(
                    f"{provider_request_id}:{len(candidates)}:{canonical_url}".encode("utf-8")
                ).hexdigest()
                candidates.append(SourceDiscoveryCandidate(
                    canonical_url=canonical_url,
                    canonical_source_identity=source_identity,
                    title=raw_title.strip(),
                    result_identity=f"anthropic-search:{result_identity}",
                    observed_at=observed_at,
                ))
        if not candidates:
            raise ValueError("source discovery returned no controlled-fetch-compatible results")
        raw_usage = _value(response, "usage")
        server = _value(raw_usage, "server_tool_use")
        usage = Usage(
            input_tokens=int(_value(raw_usage, "input_tokens", 0)),
            output_tokens=int(_value(raw_usage, "output_tokens", 0)),
            cache_read_tokens=int(_value(raw_usage, "cache_read_input_tokens", 0)),
            cache_write_tokens=int(_value(raw_usage, "cache_creation_input_tokens", 0)),
            web_search_requests=int(_value(server, "web_search_requests", 0)),
        )
        return SourceDiscoveryResponse(
            candidates=tuple(candidates[:request.max_results]),
            returned_model_id=str(_value(response, "model", self._model)),
            request_id=provider_request_id,
            usage=usage,
            port_name="anthropic_structured_web_search_v1",
        )

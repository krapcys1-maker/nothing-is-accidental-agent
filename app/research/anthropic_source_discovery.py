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
from app.llm.anthropic_provider_contract import ARTICLE_RESEARCH_INFERENCE_CONFIG
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


MAX_DISCOVERY_SEARCH_ROUNDS = 6


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
            thinking={"type": ARTICLE_RESEARCH_INFERENCE_CONFIG.thinking_type},
            output_config={"effort": ARTICLE_RESEARCH_INFERENCE_CONFIG.effort},
            tools=[{
                "type": "web_search_20250305", "name": "web_search",
                # Search rounds, not results.  Every round resends the whole
                # accumulated context, so cost grows superlinearly in rounds:
                # one observed discovery billed 3,385 then 32,584 then 61,289
                # input tokens for a single job.  Tying this to max_results made
                # asking for more candidates quietly buy more round trips.  A
                # bounded number of searches still returns ten sources.
                "max_uses": min(request.max_results, MAX_DISCOVERY_SEARCH_ROUNDS),
            }],
            messages=[{"role": "user", "content": (
                f"Find exactly {request.max_results} authoritative sources for this "
                "research question. Every source must be publicly fetchable without "
                "login or subscription and must be an HTML or plain-text page, never a "
                "PDF, and must be readable by a plain HTTP client (no bot protection). "
                "Use at least three different organisations. At least two must be "
                "PRIMARY: the originating record itself - the study, report, dataset, "
                "official statistic, regulator page or first-party company statement - "
                "not press coverage of it. If an article cites a study, return the "
                "study's own page.\n"
                "The question asserts a MECHANISM - that something happens because of "
                "a specific incentive, rule or constraint. Rule text alone cannot "
                "evidence why anyone behaves a certain way, and a corpus of pure rule "
                "statements produces a confident-sounding article with nothing behind "
                "it. So at least two sources must speak to the WHY, and both must be "
                "INSTITUTIONAL: a government or agency impact assessment, a "
                "consultation or its published response, a regulator's decision or "
                "review, a national audit or public-accounts report, a "
                "post-implementation evaluation, an official inquiry, a standards "
                "body, or peer-reviewed academic work. A vendor, supplier, "
                "consultancy or service-provider page does NOT count toward these two, "
                "however well it describes the incentive - a seller explaining why its "
                "own product gets bought is marketing, and a corpus leaning on it "
                "scores as weak sourcing even when the reasoning sounds right. Return "
                "such pages only as extra context beyond the required two. At least "
                "one source must carry quantified data - figures, rates, volumes or "
                "shares - not only description.\n"
                "If the evidence for the asserted mechanism does not appear to exist, "
                "return the sources that bear on it anyway, including any that "
                "contradict the premise. Do not substitute topically adjacent pages "
                "that merely restate the rule.\n"
                "Never return federalregister.gov, "
                "regulations.gov, congress.gov, fsis.usda.gov, ec.europa.eu, "
                "sciencedirect.com, tandfonline.com, or academia.edu. Use no more than "
                "the available search calls. Source selection only; do not synthesize "
                "claims.\n" + request.query
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
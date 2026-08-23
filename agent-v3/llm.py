"""Jedyna warstwa między `run.py` a dostawcą.

Robi cztery rzeczy i nic więcej: sprawdza warunki przed płatnym wywołaniem,
rezerwuje ekspozycję, woła model i atomowo rozlicza koszt. Rezerwacja powstaje
przed dispatch, więc śmierć procesu ani niepełny strumień nie mogą udawać zera.
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any

import anthropic
import httpx

import capabilities
import config
import db
import operational_day


class BudgetExceeded(RuntimeError):
    pass


class PreflightFailed(RuntimeError):
    pass


class Truncated(RuntimeError):
    """Odpowiedź ucięta na suficie tokenów — czytelnie, zamiast błędu JSON-a.

    Pierwszy test seryjny padł na `JSONDecodeError: Expecting ',' delimiter`
    w połowie odpowiedzi DeepSeeka. Przyczyna była o piętro wyżej: prompt prosił
    o więcej, niż mieścił sufit.
    """


class SearchLimitExceeded(RuntimeError):
    """Dostawca zakończył płatny call, ale przekroczył limit narzędzia."""


def _provider_for_model(model: str) -> str:
    if model.startswith("deepseek"):
        return "deepseek"
    if model == config.IMAGE_MODEL:
        return "openai"
    return "anthropic"


def _preflight(purpose: str, conn: sqlite3.Connection, run_id: int | None) -> None:
    """Warunki, które decydują, czy wywołanie może się w ogóle udać.

    Sprawdzane ZANIM pójdą pieniądze. Jedno zaniedbanie tej zasady kosztowało
    starego agenta 0,85 USD na eksperymencie niemożliwym od pierwszej sekundy.
    """
    model = config.MODEL_FOR[purpose]
    if model in (config.CLAUDE, config.SONNET, config.FABLE) and not config.ANTHROPIC_API_KEY:
        raise PreflightFailed("brak AGENT_V3_ANTHROPIC_API_KEY w agent-v3/.env")
    if model.startswith("deepseek") and not config.DEEPSEEK_API_KEY:
        raise PreflightFailed("brak AGENT_V3_DEEPSEEK_API_KEY w agent-v3/.env")
    if model == config.IMAGE_MODEL and not config.OPENAI_API_KEY:
        raise PreflightFailed("brak AGENT_V3_OPENAI_API_KEY w agent-v3/.env")
    if model != config.IMAGE_MODEL and model not in config.PRICING:
        raise PreflightFailed(f"model {model!r} nie ma zweryfikowanego cennika")

    if purpose not in config.MAX_TOKENS and purpose not in config.BEZ_TOKENOW:
        raise PreflightFailed(f"brak sufitu tokenów dla etapu {purpose!r}")

def _reserve_model_call(
    purpose: str, conn: sqlite3.Connection, run_id: int | None,
) -> int:
    """Rezerwuje koszt przez jedyny atomowy interfejs runtime."""
    model = config.MODEL_FOR[purpose]
    provider = _provider_for_model(model)
    current = datetime.now(timezone.utc)
    day_limit = month_limit = None
    day_start = day_end = month_start = month_end = None
    if not config.NO_LIMIT:
        editorial_date = operational_day.editorial_date(current)
        day_bounds = operational_day.boundaries(editorial_date)
        month_bounds = operational_day.month_boundaries(editorial_date)
        day_start, day_end = (
            value.isoformat(timespec="seconds") for value in day_bounds)
        month_start, month_end = (
            value.isoformat(timespec="seconds") for value in month_bounds)
        day_limit = float(config.DAILY_LIMIT_USD)
        month_limit = float(config.MONTHLY_LIMIT_USD)
    try:
        call_id, _reserved = db.reserve_model_budget(
            conn,
            run_id=run_id,
            provider=provider,
            model=model,
            purpose=purpose,
            at=current.isoformat(timespec="microseconds"),
            run_limit_usd=float(config.RUN_LIMIT_USD),
            day_limit_usd=day_limit,
            day_start=day_start,
            day_end=day_end,
            month_limit_usd=month_limit,
            month_start=month_start,
            month_end=month_end,
            fixed_price_usd=(float(config.IMAGE_PRICE_USD)
                             if purpose == "obraz" else None),
        )
    except db.ModelBudgetExceeded as exc:
        raise BudgetExceeded(str(exc)) from exc
    return call_id


def _cost(model: str, tokens_in: int, tokens_out: int, web_searches: int,
          cache_hit: int = 0) -> tuple[float, bool]:
    # DeepSeek liczy od 2026-08-16 wg pory doby, wiec stawke bierzemy na moment
    # wywolania, a nie ze stalej. Roznica miedzy szczytem a reszta doby to
    # dwukrotnosc — na tyle duzo, ze usrednianie zafalszowaloby zapis.
    if model.startswith("deepseek"):
        stawka = config.stawka_deepseek(model)
        # KLUCZ `cache` TEZ, i to nie jest kosmetyka. Bez niego linijka nizej
        # robi `price.get("cache", price["in"])` i wycenia trafienia w cache
        # stawka WEJSCIOWA — czyli trzydziestokrotnie za drogo u pro ($0,66
        # zamiast $0,022).
        #
        # `stawka_deepseek` zwraca ten klucz swiadomie i ma przy nim komentarz
        # o tej samej pomylce. Poprawka zatrzymala sie jednak w polowie drogi:
        # funkcja zaczela go oddawac, a `_cost` nadal go nie przepisywal, wiec
        # nic sie nie zmienilo. Blad zglosilem jako naprawiony, a nie byl.
        price = {"in": stawka["in"], "out": stawka["out"],
                 "cache": stawka["cache"],
                 "verified": config.PRICING[model]["verified"]}
    else:
        price = config.stawka_anthropic(model)
    # Trafienia w cache platne osobno i ~120x taniej. `tokens_in` liczymy jako
    # miss, bo tak podaje je dostawca po odjeciu trafien.
    usd = (tokens_in / 1_000_000 * price["in"]
           + tokens_out / 1_000_000 * price["out"]
           + cache_hit / 1_000_000 * price.get("cache", price["in"]))
    # Osobna opłata za wyszukiwanie jest cennikiem Anthropic. U DeepSeeka
    # wyszukiwanie mieści się w tokenach — doliczanie tu $10/1000 zawyżałoby
    # zapis finansowy, a zmyślonej kwoty w księgach być nie może.
    if model in (config.CLAUDE, config.SONNET):
        usd += web_searches / 1_000 * config.WEB_SEARCH_USD_PER_1K
    return round(usd, 6), bool(price["verified"])


def _log(purpose: str, model: str, tin: int, tout: int, searches: int, usd: float,
         verified: bool) -> None:
    flag = "" if verified else "  [STAWKA NIEPOTWIERDZONA]"
    print(
        f"  [{purpose}] {model}  wej={tin} wyj={tout}"
        f"{f' szukania={searches}' if searches else ''}"
        f"  ${usd:.4f}{flag}",
        flush=True,
    )


def _anthropic_message_result(
    message: Any, purpose: str,
) -> tuple[str, int, int, int, list[str]]:
    """Wspólne rozliczenie Messages: Anthropic oraz zgodny transport DeepSeek."""
    if message.stop_reason == "refusal":
        raise PreflightFailed(f"dostawca odmówił: {message.stop_details}")
    if message.stop_reason == "max_tokens":
        raise Truncated(
            f"odpowiedź ucięta na suficie {config.MAX_TOKENS[purpose]} tokenów "
            f"dla etapu {purpose!r} — sufit liczy się z kontraktu w config.py, "
            "więc kontrakt prosi o więcej, niż sufit mieści"
        )

    text = "".join(b.text for b in message.content if b.type == "text")
    searches = 0
    server_tool_use = getattr(message.usage, "server_tool_use", None)
    if server_tool_use is not None:
        searches = getattr(server_tool_use, "web_search_requests", 0) or 0

    # URL-e, które wyszukiwarka NAPRAWDĘ zwróciła. Sam JSON od modelu nie
    # wystarcza: zmyślony adres wygląda w nim identycznie jak prawdziwy, a
    # kosztuje nieudane pobranie i zafałszowany korpus.
    urls: list[str] = []
    for block in message.content:
        if getattr(block, "type", "") != "web_search_tool_result":
            continue
        content = getattr(block, "content", None)
        if not isinstance(content, list):
            continue  # błąd narzędzia zwraca obiekt, nie listę
        for result in content:
            url = getattr(result, "url", None)
            if isinstance(url, str):
                urls.append(url)

    return text, message.usage.input_tokens, message.usage.output_tokens, searches, urls


def _call_claude(
    purpose: str, system: str, user: str, web_search: bool
) -> tuple[str, int, int, int, list[str]]:
    model = config.MODEL_FOR[purpose]
    client = anthropic.Anthropic(
        api_key=config.ANTHROPIC_API_KEY,
        timeout=config.timeout_for(config.MAX_TOKENS[purpose]),
        max_retries=0,  # ponowienie płatnego wywołania to decyzja, nie domyślka
    )
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": config.MAX_TOKENS[purpose],
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    # `effort` istnieje na Opusie 5, Sonnecie 5 i Fable 5.
    if purpose in config.EFFORT and model in (config.CLAUDE, config.SONNET, config.FABLE):
        kwargs["output_config"] = {"effort": config.EFFORT[purpose]}
    if web_search:
        # max_uses JEST OBOWIĄZKOWE. Bez niego model robił 17, potem 31 rund
        # wyszukiwania, a każda runda przesyła całą rozmowę od nowa jako wejście
        # — 164 411 tokenów wejścia i $1,33 za jeden etap. Ograniczona liczba
        # wyszukiwań i tak zwraca dziesięć źródeł.
        kwargs["tools"] = [{
            "type": config.WEB_SEARCH_TOOL[model],
            "name": "web_search",
            "max_uses": config.DISCOVERY_MAX_SEARCHES,
        }]

    # Strumień zawsze: sufity są duże, a myślenie na Opusie 5 jest domyślnie
    # włączone i liczy się jak wyjście, więc bez strumienia grozi timeout HTTP.
    with client.messages.stream(**kwargs) as stream:
        message = stream.get_final_message()
    return _anthropic_message_result(message, purpose)


def _call_deepseek_anthropic_search(
    purpose: str, system: str, user: str,
    collect_trace: list[dict[str, Any]] | None = None,
) -> tuple[str, int, int, int, list[str]]:
    """DeepSeek web search przez oficjalny transport Anthropic z `max_uses`.

    E-020 dowiódł, że `/responses` ignoruje limit zapisany w prompcie: wykonał
    22 wyszukiwania przy maksimum 8. Ten endpoint zachowuje provider, model i
    routing, ale przenosi limit do kontraktu narzędzia wykonywanego na serwerze.
    """
    client = anthropic.Anthropic(
        api_key=config.DEEPSEEK_API_KEY,
        base_url=config.DEEPSEEK_ANTHROPIC_BASE_URL,
        timeout=config.timeout_for(config.MAX_TOKENS[purpose]),
        max_retries=0,
    )
    kwargs: dict[str, Any] = {
        "model": config.MODEL_FOR[purpose],
        "max_tokens": config.MAX_TOKENS[purpose],
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "output_config": {"effort": config.DEEPSEEK_EFFORT},
        "tools": [{
            "type": config.DEEPSEEK_WEB_SEARCH_TOOL,
            "name": "web_search",
            "max_uses": config.DISCOVERY_MAX_SEARCHES,
        }],
    }
    search_trace: dict[str, Any] | None = None
    if collect_trace is not None:
        search_trace = {
            "request_kind": "web_search",
            "system": system,
            "user": user,
            "response": None,
            "tokens_in": None,
            "tokens_out": None,
            "web_searches": None,
            "search_result_urls": [],
            "state": "DISPATCH_STARTED",
        }
        collect_trace.append(search_trace)
    try:
        with client.messages.stream(**kwargs) as stream:
            message = stream.get_final_message()
    except BaseException as exc:
        if search_trace is not None:
            search_trace["state"] = "FAILED_WITHOUT_FINAL_USAGE"
            search_trace["error"] = f"{type(exc).__name__}: {exc}"[:500]
        raise
    text, tin, tout, searches, urls = _anthropic_message_result(message, purpose)
    if search_trace is not None:
        search_trace.update({
            "response": text, "tokens_in": tin, "tokens_out": tout,
            "web_searches": searches,
            "search_result_urls": list(dict.fromkeys(urls)),
            "state": "COMPLETED_WITH_USAGE", "error": None,
        })
    if not urls:
        raise Truncated(
            f"DeepSeek wykonał {searches} wyszukiwań, ale nie zwrócił adresów"
        )
    print(
        f"  [{purpose}] wybieram wyłącznie z {len(set(urls))} adresów "
        "zwróconych przez wyszukiwarkę",
        flush=True,
    )
    picked, tin2, tout2, _selector_user = _deepseek_pick_from_urls(
        purpose, system, user, urls, draft=text, collect_trace=collect_trace,
    )
    return picked, tin + tin2, tout + tout2, searches, urls


def _call_deepseek_responses(
    purpose: str, system: str, user: str
) -> tuple[str, int, int, int, list[str]]:
    """DeepSeek przez /responses z server-side `web_search`.

    Jedyny tani sposób na dyskoverię. Sprawdzone na żywo: realnie wykonuje
    wyszukiwania i zwraca prawdziwe adresy, w przeciwieństwie do Haiku i Sonneta,
    które wypisywały je z pamięci.
    """
    request_json = {
            "model": config.MODEL_FOR[purpose],
            "instructions": system,
            "input": user,
            "tools": [{"type": "web_search"}],
            # `auto`, nie wymuszenie. Wymuszone `{"type": "web_search"}` kazało
            # modelowi wołać narzędzie w kółko — 15 wyszukiwań i ani jednego
            # zdania odpowiedzi. Nakaz szukania siedzi w prompcie.
            "tool_choice": "auto",
            # BEZ tego model przepala cały budżet wyjścia na rozumowanie
            # i wyszukiwanie, a bloku `message` nigdy nie tworzy: 11 wyszukiwań,
            # status "completed", zero tekstu. Tokeny rozumowania liczą się do
            # `max_output_tokens`, więc musi zostać miejsce na odpowiedź.
            "reasoning": {"effort": config.DEEPSEEK_EFFORT},
            "max_output_tokens": config.MAX_TOKENS[purpose],
            # Tak samo jak chat/completions: długie oczekiwanie na jeden
            # buforowany JSON kończyło się po stronie pośredniej jako
            # ``incomplete chunked read``. Responses API ma własne zdarzenia
            # SSE i terminalne ``response.completed`` z pełnym obiektem,
            # usage oraz wynikami narzędzia.
            "stream": True,
        }

    completed: dict[str, Any] | None = None
    partial_text: list[str] = []
    response_id: str | None = None
    response: httpx.Response | None = None
    event_name: str | None = None
    try:
        with httpx.stream(
            "POST",
            f"{config.DEEPSEEK_BASE_URL}/responses",
            headers={"Authorization": f"Bearer {config.DEEPSEEK_API_KEY}"},
            json=request_json,
            timeout=config.timeout_for(config.MAX_TOKENS[purpose]) * 3,
        ) as response:
            response.raise_for_status()
            for raw_line in response.iter_lines():
                line = raw_line.strip()
                if not line:
                    event_name = None
                    continue
                if line.startswith(":"):
                    continue
                if line.startswith("event:"):
                    event_name = line[6:].strip()
                    continue
                if not line.startswith("data:"):
                    raise httpx.RemoteProtocolError(
                        "DeepSeek Responses SSE line without event/data prefix",
                        request=response.request,
                    )
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    event = json.loads(data)
                except json.JSONDecodeError as exc:
                    raise httpx.RemoteProtocolError(
                        f"invalid DeepSeek Responses SSE JSON at char {exc.pos}",
                        request=response.request,
                    ) from exc
                if not isinstance(event, dict):
                    raise httpx.RemoteProtocolError(
                        "DeepSeek Responses SSE event is not an object",
                        request=response.request,
                    )
                event_type = str(event.get("type") or event_name or "")
                candidate = event.get("response")
                if isinstance(candidate, dict) and isinstance(candidate.get("id"), str):
                    response_id = candidate["id"]
                if event_type == "response.output_text.delta" and isinstance(
                    event.get("delta"), str
                ):
                    partial_text.append(event["delta"])
                elif event_type == "response.completed":
                    if not isinstance(candidate, dict):
                        raise httpx.RemoteProtocolError(
                            "response.completed lacks a response object",
                            request=response.request,
                        )
                    completed = candidate
                elif event_type in {"response.failed", "error"}:
                    detail = event.get("error") or candidate or event
                    raise httpx.RemoteProtocolError(
                        f"DeepSeek Responses SSE terminal failure: {detail}",
                        request=response.request,
                    )
    except httpx.RemoteProtocolError as exc:
        request = getattr(exc, "request", None)
        if request is None and response is not None:
            request = response.request
        raise httpx.RemoteProtocolError(
            f"{exc}; DeepSeek Responses SSE partial_content_chars="
            f"{sum(len(part) for part in partial_text)} "
            f"response_id={response_id or 'unknown'}",
            request=request,
        ) from exc

    if completed is None:
        assert response is not None
        raise httpx.RemoteProtocolError(
            "DeepSeek Responses SSE ended without response.completed; "
            f"partial_content_chars={sum(len(part) for part in partial_text)} "
            f"response_id={response_id or 'unknown'}",
            request=response.request,
        )
    if completed.get("status") != "completed":
        raise Truncated(
            f"DeepSeek Responses zakończył etap {purpose!r} ze statusem "
            f"{completed.get('status')!r}: {completed.get('incomplete_details')!r}"
        )
    payload = completed

    text_parts: list[str] = []
    urls: list[str] = []
    searches = 0

    def walk(node: Any) -> None:
        nonlocal searches
        if isinstance(node, dict):
            if node.get("type") == "web_search_call":
                searches += 1
            if node.get("type") in {"output_text", "text"} and isinstance(
                node.get("text"), str
            ):
                text_parts.append(node["text"])
            for key, value in node.items():
                if key == "url" and isinstance(value, str):
                    # adresy niosą doklejony fragment #ws_call_id=...
                    urls.append(value.split("#ws_call_id=")[0])
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload.get("output", []))
    text = payload.get("output_text") or "".join(text_parts)
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        assert response is not None
        raise httpx.RemoteProtocolError(
            "DeepSeek Responses response.completed lacks usage",
            request=response.request,
        )

    # DeepSeek bywa, że przeszukuje i przeszukuje, a bloku `message` nie tworzy
    # — 14 i 24 wyszukiwania kończyły się odpowiedzią, 36 już nie. Ale adresy
    # z tych wyszukiwań SĄ w odpowiedzi i są opłacone. Zamiast wyrzucać je do
    # kosza i płacić drugi raz, prosimy o sam wybór, bez narzędzi.
    if not text.strip() and urls:
        print(
            f"  [{purpose}] {searches} wyszukiwań bez odpowiedzi — wybieram "
            f"z {len(set(urls))} znalezionych adresów drugim wywołaniem",
            flush=True,
        )
        text, tin2, tout2, _selector_user = _deepseek_pick_from_urls(
            purpose, system, user, urls,
        )
        return (
            text,
            int(usage.get("input_tokens", 0)) + tin2,
            int(usage.get("output_tokens", 0)) + tout2,
            searches,
            urls,
        )

    if not text.strip():
        raise Truncated(
            f"DeepSeek wykonał {searches} wyszukiwań i nie zwrócił ani tekstu, "
            f"ani adresów (status={payload.get('status')!r})"
        )
    return (
        text,
        int(usage.get("input_tokens", 0)),
        int(usage.get("output_tokens", 0)),
        searches,
        urls,
    )


def _deepseek_pick_from_urls(
    purpose: str, system: str, user: str, urls: list[str], *, draft: str = "",
    collect_trace: list[dict[str, Any]] | None = None,
) -> tuple[str, int, int, str]:
    """Drugie, tanie wywołanie: wybierz z adresów, które wyszukiwanie już zwróciło.

    Bez narzędzi, więc nie ma jak zapętlić się w szukaniu.
    """
    unique: list[str] = []
    url_chars = 0
    for candidate in dict.fromkeys(urls):
        if not isinstance(candidate, str):
            continue
        added = len(candidate) + 1
        if url_chars + added > config.DISCOVERY_SELECTOR_MAX_URL_CHARS_TOTAL:
            break
        unique.append(candidate)
        url_chars += added
    if not unique:
        raise Truncated("selektor exact-URL nie dostał żadnego adresu")
    selector_user = (
        f"{user}\n\n---\n\nA search has already been run. Below are its "
        "draft and the complete list of addresses actually returned by the "
        "search tool in this run. Audit the draft and return the final JSON. "
        "Do not search again, reconstruct an address, or use any URL absent "
        "from EXACT SEARCH RESULT URLS. Preserve all quality and evidence-role "
        "requirements from the original task. If a required role is not "
        "available in the exact list, return the best honest subset instead "
        "of inventing it.\n\nSEARCH DRAFT:\n"
        f"{draft or '[no draft text]'}\n\nEXACT SEARCH RESULT URLS:\n"
        + "\n".join(unique)
    )
    selector_trace: dict[str, Any] | None = None
    if collect_trace is not None:
        selector_trace = {
            "request_kind": "exact_url_selector",
            "system": system,
            "user": selector_user,
            "response": None,
            "tokens_in": None,
            "tokens_out": None,
            "web_searches": 0,
            "search_result_urls": list(unique),
            "state": "DISPATCH_STARTED",
        }
        collect_trace.append(selector_trace)
    try:
        response = httpx.post(
            f"{config.DEEPSEEK_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {config.DEEPSEEK_API_KEY}"},
            json={
                # MODEL Z ROUTINGU, nie zaszyta stala. Bylo tu config.DEEPSEEK,
                # wiec każdy etap bez wyszukiwania jechał na flashu niezależnie
                # od routingu, a koszt księgowano po stawce pro.
                "model": config.MODEL_FOR[purpose],
                "max_tokens": config.MAX_TOKENS[purpose],
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": selector_user},
                ],
            },
            timeout=config.timeout_for(config.MAX_TOKENS[purpose]),
        )
        response.raise_for_status()
        payload = response.json()
    except BaseException as exc:
        if selector_trace is not None:
            selector_trace["state"] = "FAILED_WITHOUT_FINAL_USAGE"
            selector_trace["error"] = f"{type(exc).__name__}: {exc}"[:500]
        raise
    usage = payload.get("usage", {})
    picked = payload["choices"][0]["message"]["content"]
    tin = int(usage.get("prompt_tokens", 0))
    tout = int(usage.get("completion_tokens", 0))
    if selector_trace is not None:
        selector_trace.update({
            "response": picked, "tokens_in": tin, "tokens_out": tout,
            "state": "COMPLETED_WITH_USAGE", "error": None,
        })
    return (
        picked, tin, tout,
        selector_user,
    )


def _call_deepseek(
    purpose: str, system: str, user: str,
) -> tuple[str, int, int, int, int]:
    request_json = {
        # MODEL Z ROUTINGU, nie zaszyta stala. Bylo tu config.DEEPSEEK, wiec
        # kazdy etap bez wyszukiwania jechal na flashu niezaleznie od tego,
        # co mowil MODEL_FOR — a koszt ksiegowalismy po stawce pro.
        "model": config.MODEL_FOR[purpose],
        "max_tokens": config.MAX_TOKENS[purpose],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        # Trzy live scouty przez odpowiedz buforowana konczyly sie po 120-181 s
        # identycznym ``incomplete chunked read`` i bez usage. Oficjalny
        # kontrakt DeepSeek przewiduje SSE oraz osobny koncowy chunk usage.
        # Dla dlugiego rozumowania tokeny musza podtrzymywac polaczenie zamiast
        # czekac za jednym wielkim JSON-em do konca generacji.
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    content_parts: list[str] = []
    usage: dict[str, Any] | None = None
    finish_reason: str | None = None
    response_id: str | None = None
    done = False
    response: httpx.Response | None = None
    try:
        with httpx.stream(
            "POST",
            f"{config.DEEPSEEK_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {config.DEEPSEEK_API_KEY}"},
            json=request_json,
            timeout=config.timeout_for(config.MAX_TOKENS[purpose]),
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                line = line.strip()
                if not line or line.startswith(":"):
                    continue
                if not line.startswith("data:"):
                    raise httpx.RemoteProtocolError(
                        "DeepSeek SSE line without data prefix",
                        request=response.request,
                    )
                data = line[5:].strip()
                if data == "[DONE]":
                    done = True
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError as exc:
                    raise httpx.RemoteProtocolError(
                        f"invalid DeepSeek SSE JSON at char {exc.pos}",
                        request=response.request,
                    ) from exc
                if not isinstance(chunk, dict):
                    raise httpx.RemoteProtocolError(
                        "DeepSeek SSE chunk is not an object",
                        request=response.request,
                    )
                if isinstance(chunk.get("id"), str):
                    response_id = chunk["id"]
                if isinstance(chunk.get("usage"), dict):
                    usage = chunk["usage"]
                choices = chunk.get("choices") or []
                if choices:
                    choice = choices[0]
                    delta = choice.get("delta") or {}
                    if isinstance(delta.get("content"), str):
                        content_parts.append(delta["content"])
                    if choice.get("finish_reason") is not None:
                        finish_reason = str(choice["finish_reason"])
    except httpx.RemoteProtocolError as exc:
        request = getattr(exc, "request", None)
        if request is None and response is not None:
            request = response.request
        raise httpx.RemoteProtocolError(
            f"{exc}; DeepSeek SSE partial_content_chars="
            f"{sum(len(part) for part in content_parts)} "
            f"response_id={response_id or 'unknown'}",
            request=request,
        ) from exc

    if not done:
        assert response is not None
        raise httpx.RemoteProtocolError(
            "DeepSeek SSE ended without data: [DONE]",
            request=response.request,
        )
    if finish_reason == "length":
        raise Truncated(
            f"odpowiedź ucięta na suficie {config.MAX_TOKENS[purpose]} tokenów "
            f"dla etapu {purpose!r} — bez tego wychodzi z tego niedomknięty JSON"
        )
    if finish_reason not in {None, "stop"}:
        raise Truncated(
            f"DeepSeek przerwał etap {purpose!r}: finish_reason={finish_reason!r}"
        )
    if usage is None:
        assert response is not None
        raise httpx.RemoteProtocolError(
            "DeepSeek SSE reached DONE without the requested usage chunk",
            request=response.request,
        )
    text = "".join(content_parts)
    if not text.strip():
        raise Truncated(f"DeepSeek nie zwrócił treści dla etapu {purpose!r}")
    trafienia = int(usage.get("prompt_cache_hit_tokens", 0))
    pudla = int(usage.get("prompt_cache_miss_tokens",
                          usage.get("prompt_tokens", 0) - trafienia))
    return (
        text,
        pudla,
        int(usage.get("completion_tokens", 0)),
        0,
        trafienia,
    )


def przejsciowy(exc: BaseException) -> bool:
    """Czy ten błąd ma szansę minąć sam.

    Rozróżnienie, które decyduje o tym, czy ponowienie jest dokończeniem, czy
    paleniem pieniędzy:

    PRZEJŚCIOWE — wywołanie się NIE ODBYŁO albo dostawca chwilowo nie dał rady:
    zerwana sieć, przekroczony czas, 429, 5xx. Ponowienie takiego wywołania nie
    jest decyzją, tylko dokończeniem tego, co miało się zdarzyć.

    TRWAŁE — wywołanie się odbyło i skończyło źle: odmowa dostawcy, zły klucz,
    przekroczony budżet, odpowiedź ucięta na suficie. Powtórzy się identycznie,
    więc ponawianie kosztuje i nie zmienia nic.
    """
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)):
        return True
    cause = getattr(exc, "__cause__", None)
    if cause is not None and cause is not exc:
        return przejsciowy(cause)
    # ReadTimeout, ReadError, RemoteProtocolError, HTTP 429/5xx i każdy błąd
    # po rozpoczęciu odpowiedzi mogą oznaczać, że dostawca już wygenerował i
    # naliczył wynik. Bez provider-side idempotency automatyczny retry byłby
    # nowym płatnym wywołaniem, nie dokończeniem poprzedniego.
    return False


def call(
    purpose: str,
    system: str,
    user: str,
    *,
    conn: sqlite3.Connection,
    run_id: int | None = None,
    web_search: bool = False,
    collect_urls: list[str] | None = None,
    collect_trace: list[dict[str, Any]] | None = None,
) -> str:
    """Woła model właściwy dla etapu i zapisuje koszt. Zwraca tekst odpowiedzi.

    `collect_urls`, jeśli podane, zostanie wypełnione adresami, które realnie
    zwróciła wyszukiwarka — do sprawdzenia, czy model nie zmyślił URL-a.
    """
    if config.DRY_RUN:
        print(f"  [{purpose}] DRY_RUN — wywołanie pominięte", flush=True)
        return ""

    try:
        capabilities.require(capabilities.Capability.MODEL_CALL)
    except capabilities.CapabilityDenied as exc:
        raise PreflightFailed(str(exc)) from exc
    _preflight(purpose, conn, run_id)
    model = config.MODEL_FOR[purpose]
    provider = _provider_for_model(model)
    call_id = _reserve_model_call(purpose, conn, run_id)

    for proba in range(1, config.PONOWIENIA + 2):
        try:
            if provider == "anthropic":
                text, tin, tout, searches, urls = _call_claude(
                    purpose, system, user, web_search)
                cache_hit = 0
            elif web_search:
                text, tin, tout, searches, urls = _call_deepseek_anthropic_search(
                    purpose, system, user, collect_trace=collect_trace)
                cache_hit = 0
            else:
                text, tin, tout, searches, cache_hit = _call_deepseek(
                    purpose, system, user)
                urls = []
            if collect_urls is not None:
                collect_urls.extend(urls)
            break
        except Exception as exc:
            if przejsciowy(exc) and proba <= config.PONOWIENIA:
                czekaj = config.PONOWIENIE_ODSTEP_S * 2 ** (proba - 1)
                print(f"  [{purpose}] {type(exc).__name__} — przejściowy, "
                      f"ponawiam za {czekaj}s ({proba}/{config.PONOWIENIA})",
                      flush=True)
                time.sleep(czekaj)
                continue
            note = f"{type(exc).__name__}: {exc}"[:500]
            if przejsciowy(exc):
                # Wyczerpano wyłącznie błędy sprzed dispatch; koszt jest znanym 0.
                db.settle_reserved_call(
                    conn, call_id, tokens_in=0, tokens_out=0, cache_hit=0,
                    web_searches=0, cost_usd=0.0, price_verified=False,
                    ok=False, note=note,
                )
            else:
                db.mark_call_cost_unknown(conn, call_id, note=note)
            raise

    trafienia = locals().get("cache_hit", 0) or 0
    search_limit_note = None
    if web_search and searches > config.DISCOVERY_MAX_SEARCHES:
        search_limit_note = (
            f"SearchLimitExceeded: dostawca wykonał {searches} wyszukiwań "
            f"przy limicie {config.DISCOVERY_MAX_SEARCHES}"
        )
    try:
        usd, verified = _cost(model, tin, tout, searches, trafienia)
        db.settle_reserved_call(
            conn, call_id, tokens_in=tin, tokens_out=tout, cache_hit=trafienia,
            web_searches=searches, cost_usd=usd,
            price_verified=verified, ok=search_limit_note is None,
            note=search_limit_note,
        )
    except Exception as exc:
        # Transport się udał, więc nawet lokalny błąd rozliczenia zachowuje
        # ekspozycję do rekoncyliacji zamiast zostawiać martwe RESERVED.
        row = conn.execute(
            "SELECT cost_status FROM calls WHERE id=?", (call_id,)
        ).fetchone()
        if row is not None and row["cost_status"] == "RESERVED":
            db.mark_call_cost_unknown(
                conn, call_id, note=f"{type(exc).__name__}: {exc}"[:500]
            )
        raise
    _log(purpose, model, tin, tout, searches, usd, verified)
    if search_limit_note is not None:
        raise SearchLimitExceeded(search_limit_note)
    return text


def obraz(
    opis: str, *, conn: sqlite3.Connection, run_id: int | None = None
) -> bytes:
    """Generuje grafikę do artykułu i zapisuje jej koszt tam, gdzie resztę.

    Obraz idzie przez tę samą warstwę co tekst nie dla elegancji, tylko dlatego,
    że inaczej wypadłby z licznika: wyłącznik, limit na przebieg i dzienny sufit
    wydatków siedzą w `_preflight`, a nie w każdym wywołaniu z osobna.
    """
    if config.DRY_RUN:
        print("  [obraz] DRY_RUN — wywołanie pominięte", flush=True)
        return b""
    try:
        capabilities.require(capabilities.Capability.MODEL_CALL)
    except capabilities.CapabilityDenied as exc:
        raise PreflightFailed(str(exc)) from exc
    _preflight("obraz", conn, run_id)
    if not config.OPENAI_API_KEY:
        raise RuntimeError("brak AGENT_V3_OPENAI_API_KEY")

    import base64
    import urllib.request

    call_id = _reserve_model_call("obraz", conn, run_id)

    zadanie = json.dumps({
        "model": config.IMAGE_MODEL,
        "prompt": opis,
        "size": config.IMAGE_SIZE,
        "quality": config.IMAGE_QUALITY,
        "n": 1,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/images/generations",
        data=zadanie,
        headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}",
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=config.IMAGE_TIMEOUT_S) as odp:
            dane = json.loads(odp.read().decode("utf-8"))
        surowy = dane["data"][0]["b64_json"]
    except Exception as exc:
        db.mark_call_cost_unknown(
            conn, call_id, note=f"{type(exc).__name__}: {exc}"[:500]
        )
        raise

    usd = config.IMAGE_PRICE_USD
    db.settle_reserved_call(
        conn, call_id, tokens_in=0, tokens_out=0, cache_hit=0, web_searches=0,
        cost_usd=usd, price_verified=False, ok=True, note=config.IMAGE_SIZE,
    )
    print(f"  [obraz] {config.IMAGE_MODEL}  {config.IMAGE_SIZE}  ~${usd:.4f}", flush=True)
    return base64.b64decode(surowy)


def parse_json(text: str) -> Any:
    """Parsuje dokładnie jeden obiekt JSON, opcjonalnie w Markdown fence.

    Nie wycinamy już fragmentu od pierwszej do ostatniej klamry. Proza obok
    obiektu, duplikat klucza i niestandardowe stałe `NaN`/`Infinity` są błędem
    kontraktu, a nie tekstem do cichej naprawy.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if len(lines) < 3 or lines[-1].strip() != "```":
            raise ValueError("niedomknięty Markdown fence wokół JSON")
        if lines[0].strip().lower() not in {"```", "```json"}:
            raise ValueError("nieznany rodzaj Markdown fence")
        cleaned = "\n".join(lines[1:-1]).strip()

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplikat klucza JSON: {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"niedozwolona stała JSON: {value}")

    try:
        parsed = json.loads(
            cleaned, object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"niepoprawny pojedynczy JSON: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(
            f"korzeń odpowiedzi musi być obiektem, jest {type(parsed).__name__}")
    return parsed

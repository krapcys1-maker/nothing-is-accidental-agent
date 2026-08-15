"""Jedyna warstwa między `run.py` a dostawcą.

Robi cztery rzeczy i nic więcej: sprawdza warunki przed płatnym wywołaniem,
woła model, liczy koszt, zapisuje wywołanie. Bez rezerwacji, bez rekoncyliacji,
bez ponowień — świadomy kompromis: jeśli proces zginie w połowie wywołania,
koszt tego wywołania nie trafi do logu. Limit dzienny ogranicza szkodę.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

import anthropic
import httpx

import config
import db


class BudgetExceeded(RuntimeError):
    pass


class PreflightFailed(RuntimeError):
    pass


def _preflight(purpose: str, conn: sqlite3.Connection) -> None:
    """Warunki, które decydują, czy wywołanie może się w ogóle udać.

    Sprawdzane ZANIM pójdą pieniądze. Jedno zaniedbanie tej zasady kosztowało
    starego agenta 0,85 USD na eksperymencie niemożliwym od pierwszej sekundy.
    """
    if config.KILL_SWITCH:
        raise PreflightFailed("KILL_SWITCH=true — wywołania wstrzymane")

    model = config.MODEL_FOR[purpose]
    if model == config.CLAUDE and not config.ANTHROPIC_API_KEY:
        raise PreflightFailed("brak ANTHROPIC_API_KEY w .env")
    if model == config.DEEPSEEK and not config.DEEPSEEK_API_KEY:
        raise PreflightFailed("brak DEEPSEEK_API_KEY w .env")

    if purpose not in config.MAX_TOKENS:
        raise PreflightFailed(f"brak sufitu tokenów dla etapu {purpose!r}")

    if config.NO_LIMIT:
        return

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    month = today[:7]
    spent_today = db.spent_usd(conn, today)
    spent_month = db.spent_usd(conn, month)
    if spent_today >= config.DAILY_LIMIT_USD:
        raise BudgetExceeded(
            f"limit dzienny wyczerpany: {spent_today:.4f} / {config.DAILY_LIMIT_USD} USD"
        )
    if spent_month >= config.MONTHLY_LIMIT_USD:
        raise BudgetExceeded(
            f"limit miesięczny wyczerpany: {spent_month:.4f} / {config.MONTHLY_LIMIT_USD} USD"
        )


def _cost(model: str, tokens_in: int, tokens_out: int, web_searches: int) -> tuple[float, bool]:
    price = config.PRICING[model]
    usd = (
        tokens_in / 1_000_000 * price["in"]
        + tokens_out / 1_000_000 * price["out"]
        + web_searches / 1_000 * config.WEB_SEARCH_USD_PER_1K
    )
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


def _call_claude(
    purpose: str, system: str, user: str, web_search: bool
) -> tuple[str, int, int, int, list[str]]:
    client = anthropic.Anthropic(
        api_key=config.ANTHROPIC_API_KEY,
        timeout=config.timeout_for(config.MAX_TOKENS[purpose]),
        max_retries=0,  # ponowienie płatnego wywołania to decyzja, nie domyślka
    )
    kwargs: dict[str, Any] = {
        "model": config.CLAUDE,
        "max_tokens": config.MAX_TOKENS[purpose],
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    if purpose in config.EFFORT:
        kwargs["output_config"] = {"effort": config.EFFORT[purpose]}
    if web_search:
        kwargs["tools"] = [{"type": "web_search_20260209", "name": "web_search"}]

    # Strumień zawsze: sufity są duże, a myślenie na Opusie 5 jest domyślnie
    # włączone i liczy się jak wyjście, więc bez strumienia grozi timeout HTTP.
    with client.messages.stream(**kwargs) as stream:
        message = stream.get_final_message()

    if message.stop_reason == "refusal":
        raise PreflightFailed(f"dostawca odmówił: {message.stop_details}")

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


def _call_deepseek(purpose: str, system: str, user: str) -> tuple[str, int, int, int]:
    response = httpx.post(
        f"{config.DEEPSEEK_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {config.DEEPSEEK_API_KEY}"},
        json={
            "model": config.DEEPSEEK,
            "max_tokens": config.MAX_TOKENS[purpose],
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=config.timeout_for(config.MAX_TOKENS[purpose]),
    )
    response.raise_for_status()
    payload = response.json()
    usage = payload.get("usage", {})
    return (
        payload["choices"][0]["message"]["content"],
        int(usage.get("prompt_tokens", 0)),
        int(usage.get("completion_tokens", 0)),
        0,
    )


def call(
    purpose: str,
    system: str,
    user: str,
    *,
    conn: sqlite3.Connection,
    run_id: int | None = None,
    web_search: bool = False,
    collect_urls: list[str] | None = None,
) -> str:
    """Woła model właściwy dla etapu i zapisuje koszt. Zwraca tekst odpowiedzi.

    `collect_urls`, jeśli podane, zostanie wypełnione adresami, które realnie
    zwróciła wyszukiwarka — do sprawdzenia, czy model nie zmyślił URL-a.
    """
    _preflight(purpose, conn)
    model = config.MODEL_FOR[purpose]
    provider = "anthropic" if model == config.CLAUDE else "deepseek"

    if config.DRY_RUN:
        print(f"  [{purpose}] DRY_RUN — wywołanie pominięte", flush=True)
        return ""

    try:
        if provider == "anthropic":
            text, tin, tout, searches, urls = _call_claude(purpose, system, user, web_search)
        else:
            text, tin, tout, searches = _call_deepseek(purpose, system, user)
            urls = []
        if collect_urls is not None:
            collect_urls.extend(urls)
    except Exception as exc:
        # Koszt nieudanego wywołania bywa nieznany. Zapisujemy "nie wiadomo"
        # zamiast zgadywać kwotę — zgadnięta kwota w zapisie finansowym jest
        # gorsza niż jej brak.
        db.record_call(
            conn=conn, run_id=run_id, provider=provider, model=model, purpose=purpose,
            tokens_in=0, tokens_out=0, web_searches=0, cost_usd=0.0,
            price_verified=0, ok=0, note=f"{type(exc).__name__}: {exc}"[:500],
        )
        raise

    usd, verified = _cost(model, tin, tout, searches)
    db.record_call(
        conn=conn, run_id=run_id, provider=provider, model=model, purpose=purpose,
        tokens_in=tin, tokens_out=tout, web_searches=searches, cost_usd=usd,
        price_verified=int(verified), ok=1, note=None,
    )
    _log(purpose, model, tin, tout, searches, usd, verified)
    return text


def parse_json(text: str) -> Any:
    """Wyciąga obiekt JSON z odpowiedzi modelu.

    Modele lubią owinąć JSON w ```json. Nie robimy z tego bramki — obcinamy
    płot i parsujemy.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
        cleaned = cleaned.rsplit("```", 1)[0]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"brak JSON w odpowiedzi: {text[:200]!r}")
    return json.loads(cleaned[start : end + 1])

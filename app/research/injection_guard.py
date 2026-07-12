"""Ochrona przed prompt injection z treści źródeł.

Zasada bezpieczeństwa: treść pobrana z internetu jest NIEZAUFANYM materiałem źródłowym,
nigdy instrukcją dla agenta. Ten moduł wykrywa i neutralizuje próby wstrzyknięcia poleceń
w tekście źródeł, zanim trafią one gdziekolwiek dalej. Sam pipeline i tak wyciąga wyłącznie
ustrukturyzowane pola — polecenie ze strony nie może zmienić decyzji agenta.
"""
from __future__ import annotations

import re

_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"disregard\s+(the\s+)?(previous|prior|above)",
    r"forget\s+(everything|all|previous)",
    r"you\s+are\s+now\b",
    r"new\s+instructions?\s*:",
    r"system\s+prompt",
    r"\bassistant\s*:",
    r"\bsystem\s*:",
    r"act\s+as\b",
    r"reveal\s+(your|the)\s+(system|prompt|instructions)",
    r"override\s+(the\s+)?(rules|policy|safeguards)",
    r"set\s+confidence\s+to\s+\d",
    r"mark\s+(this\s+)?(as\s+)?(verified|confirmed)\b",
]
_COMPILED = [re.compile(p, flags=re.IGNORECASE) for p in _INJECTION_PATTERNS]
_REDACTION = "[REDACTED-INSTRUCTION]"


def contains_injection(text: str | None) -> bool:
    if not text:
        return False
    return any(rx.search(text) for rx in _COMPILED)


def neutralize(text: str | None) -> str:
    if not text:
        return ""
    out = text
    for rx in _COMPILED:
        out = rx.sub(_REDACTION, out)
    return out

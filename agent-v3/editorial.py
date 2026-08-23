"""Pamięć redakcyjna V3: treść -> wynik -> reakcje -> następna decyzja.

Moduł nie publikuje i nie woła modeli. Przechowuje fakty o pracy redakcji,
liczy wyniki względne bez jednego zbiorczego "success score" i oddaje mały
brief, który można bezpiecznie podać skautowi albo pisarzowi.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any, Iterable


EDITORIAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS content_items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id    INTEGER UNIQUE,
    run_id        INTEGER,
    external_id   TEXT,
    kind          TEXT NOT NULL,
    status        TEXT NOT NULL,
    topic         TEXT,
    title         TEXT,
    mechanism     TEXT,
    form          TEXT,
    hook          TEXT,
    canonical_url TEXT,
    created_at    TEXT NOT NULL,
    published_at  TEXT,
    UNIQUE(kind, external_id)
);

CREATE TABLE IF NOT EXISTS metric_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id  INTEGER NOT NULL,
    captured_at TEXT NOT NULL,
    horizon     TEXT NOT NULL,
    age_hours   REAL,
    followers   INTEGER,
    subscribers INTEGER,
    views       INTEGER,
    opens       INTEGER,
    likes       INTEGER,
    comments    INTEGER,
    restacks    INTEGER,
    signups     INTEGER,
    subscribes  INTEGER,
    raw_json    TEXT,
    UNIQUE(content_id, captured_at)
);

CREATE TABLE IF NOT EXISTS audience_signals (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id         INTEGER,
    target_external_id TEXT,
    external_id        TEXT,
    observed_at        TEXT NOT NULL,
    kind               TEXT NOT NULL,
    text               TEXT,
    author             TEXT,
    resolved           INTEGER NOT NULL DEFAULT 0,
    raw_json           TEXT,
    UNIQUE(external_id, kind)
);

CREATE TABLE IF NOT EXISTS editorial_observations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_key     TEXT NOT NULL UNIQUE,
    topic          TEXT,
    mechanism      TEXT,
    dimension      TEXT NOT NULL,
    observation    TEXT NOT NULL,
    evidence_count INTEGER NOT NULL DEFAULT 0,
    confidence     TEXT NOT NULL,
    first_seen_at  TEXT NOT NULL,
    last_seen_at   TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'ACTIVE',
    evidence_json  TEXT
);

CREATE TABLE IF NOT EXISTS deferred_topics (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint   TEXT NOT NULL UNIQUE,
    run_id        INTEGER,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'WAITING',
    attempts      INTEGER NOT NULL DEFAULT 1,
    topic_json    TEXT NOT NULL,
    reason        TEXT,
    missing_piece TEXT,
    research_json TEXT,
    retry_after   TEXT
);

CREATE TABLE IF NOT EXISTS article_revisions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id    INTEGER,
    run_id        INTEGER,
    created_at    TEXT NOT NULL,
    iteration     INTEGER NOT NULL,
    trigger_json  TEXT NOT NULL,
    before_json   TEXT NOT NULL,
    after_json    TEXT,
    status        TEXT NOT NULL,
    remaining_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_content_kind_status
    ON content_items(kind, status, published_at);
CREATE INDEX IF NOT EXISTS idx_snapshots_content_horizon
    ON metric_snapshots(content_id, horizon, captured_at);
CREATE INDEX IF NOT EXISTS idx_signals_content_kind
    ON audience_signals(content_id, kind, observed_at);
CREATE INDEX IF NOT EXISTS idx_deferred_status
    ON deferred_topics(status, updated_at);
"""


FACTUAL_GATES = frozenset({
    "ZMYSLONE_PRZEZYCIE",
    "NIEISTNIEJACE_BADANIE",
    "LICZBA_SPOZA_KORPUSU",
    "LICZBA_BEZ_LANCUCHA",
    "FAKT_BEZ_POKRYCIA",
    "STATYSTYKA_BEZ_ZRODLA",
})
TECHNICAL_GATES = frozenset({"KONTROLA_NIEDOSTEPNA"})

QUALITY_POLICY_VERSION = "autonomous-editorial@1"
MAX_AUTONOMOUS_REVISIONS = 2

# Polityka jest per bramka, nie per sama liczba uwag. Brak podstawy źródłowej
# nie jest problemem, który redaktor może naprawić parafrazą. Awaria wymaganej
# kontroli także nie może dostać statusu publikowalnego. Pozostałe znane wady
# są poprawialne, ale po ograniczonej liczbie iteracji kończą się kwarantanną.
EVIDENCE_QUARANTINE_GATES = frozenset({"WASKA_PODSTAWA"})
EDITORIAL_REVISION_GATES = frozenset({
    "FRAZA_Z_INSTRUKCJI",
    "ZAPOWIEDZ_GRANIC",
    "BUDZET_ZASTRZEZEN",
    "OBWIESZCZONA_POWSCIAGLIWOSC",
    "ZAKAZANE_OTWARCIE",
    "NIEWIADOME_NA_KONCU",
    "ODCISK_FORMY",
    "GESTOSC_BEATOW",
    "BRAK_ESKALACJI",
    "CZYTELNIK_NIEPRZYLAPANY",
    "OTWARCIE_ZNANE",
    "DLUGOSC_POZA_KONTRAKTEM",
})


def _gate_policy(gate: str) -> dict[str, Any]:
    if gate in FACTUAL_GATES:
        return {"domain": "EVIDENCE", "reaction": "REVISE", "severity": 100}
    if gate in EVIDENCE_QUARANTINE_GATES:
        return {"domain": "EVIDENCE", "reaction": "QUARANTINE", "severity": 100}
    if gate in TECHNICAL_GATES:
        return {"domain": "EDITORIAL", "reaction": "QUARANTINE", "severity": 100}
    if gate in EDITORIAL_REVISION_GATES:
        severity = 80 if gate in {
            "FRAZA_Z_INSTRUKCJI", "ODCISK_FORMY", "DLUGOSC_POZA_KONTRAKTEM",
        } else 40
        return {"domain": "EDITORIAL", "reaction": "REVISE", "severity": severity}
    # Nowa lub źle nazwana bramka nie może po cichu odziedziczyć statusu
    # „drobna uwaga”. Najpierw kwarantanna i jawna aktualizacja polityki.
    return {"domain": "EDITORIAL", "reaction": "QUARANTINE", "severity": 100}


_QUALITY_POLICY_MATERIAL = {
    "version": QUALITY_POLICY_VERSION,
    "max_revisions": MAX_AUTONOMOUS_REVISIONS,
    "gates": {
        gate: _gate_policy(gate)
        for gate in sorted(
            FACTUAL_GATES | TECHNICAL_GATES | EVIDENCE_QUARANTINE_GATES
            | EDITORIAL_REVISION_GATES
        )
    },
    "unknown_gate": _gate_policy("__UNKNOWN__"),
}
QUALITY_POLICY_HASH = hashlib.sha256(
    json.dumps(_QUALITY_POLICY_MATERIAL, sort_keys=True).encode("utf-8")
).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Zakłada wyłącznie dodatkowe tabele V3; danych V2 nie przepisuje."""
    conn.executescript(EDITORIAL_SCHEMA)
    conn.commit()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()[:24]


def confidence_for(sample_size: int) -> str:
    """Pewność rośnie z liczbą obserwacji, nie z tonem opisu."""
    if sample_size < 10:
        return "VERY_LOW"
    if sample_size < 30:
        return "LOW"
    if sample_size < 100:
        return "MEDIUM"
    return "HIGH"


def quality_decision(findings: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Wersjonowana decyzja autonomiczna oparta o wagę każdej bramki."""
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in findings:
        gate = str(item.get("gate") or "UNKNOWN").strip()
        detail = str(item.get("detail") or "").strip()
        key = (gate, detail)
        if key in seen:
            continue
        seen.add(key)
        policy = _gate_policy(gate)
        unique.append({"gate": gate, "detail": detail, **policy})

    factual = [x for x in unique if x["gate"] in FACTUAL_GATES]
    technical = [x for x in unique if x["gate"] in TECHNICAL_GATES]
    evidence_quarantine = [
        x for x in unique
        if x["domain"] == "EVIDENCE" and x["reaction"] == "QUARANTINE"
    ]
    editorial_quarantine = [
        x for x in unique
        if x["domain"] == "EDITORIAL" and x["reaction"] == "QUARANTINE"
    ]
    count = len(unique)
    if evidence_quarantine:
        action = "QUARANTINED_EVIDENCE"
        reason = "podstawy źródłowej nie da się naprawić redakcją tekstu"
    elif technical or editorial_quarantine:
        action = "QUARANTINED_EDITORIAL"
        reason = "wymagana kontrola lub znana polityka bramki jest niedostępna"
    elif factual:
        action = "REVISE_FACTS"
        reason = "poważna uwaga faktograficzna: " + ", ".join(
            sorted({x["gate"] for x in factual}))
    elif count:
        action, reason = "REVISE", f"{count} uwag wymaga kontrolowanej redakcji"
    else:
        action = "READY_AUTONOMOUS"
        reason = "wszystkie wymagane bramki przeszły"
    return {
        "action": action,
        "can_publish": action == "READY_AUTONOMOUS",
        "reason": reason,
        "policy_version": QUALITY_POLICY_VERSION,
        "policy_hash": QUALITY_POLICY_HASH,
        "finding_count": count,
        "factual_count": len(factual),
        "technical_count": len(technical),
        "severity_score": sum(int(x["severity"]) for x in unique),
        "findings": unique,
    }


def revision_progress(
    before: dict[str, Any], after: dict[str, Any], *, body_changed: bool,
) -> dict[str, Any]:
    """Rozstrzyga poprawę bez arbitralnej oceny modelu."""
    before_gates = {str(x.get("gate")) for x in before.get("findings") or []}
    after_gates = {str(x.get("gate")) for x in after.get("findings") or []}
    new_gates = sorted(after_gates - before_gates)
    before_score = int(before.get("severity_score") or 0)
    after_score = int(after.get("severity_score") or 0)

    if after.get("can_publish"):
        outcome = "RESOLVED"
    elif not body_changed:
        outcome = "NO_IMPROVEMENT"
    elif new_gates or after_score > before_score:
        outcome = "REGRESSION"
    elif after_score == before_score:
        outcome = "NO_IMPROVEMENT"
    else:
        outcome = "IMPROVED"
    return {
        "outcome": outcome,
        "before_score": before_score,
        "after_score": after_score,
        "new_gates": new_gates,
    }


def quarantine_after_revision(
    quality: dict[str, Any], *, reason: str,
) -> dict[str, Any]:
    """Kończy pętlę bez stanu pośredniego i bez publikacji przez fallback."""
    result = dict(quality)
    has_evidence = any(
        item.get("domain") == "EVIDENCE" for item in quality.get("findings") or []
    )
    result["action"] = (
        "QUARANTINED_EVIDENCE" if has_evidence else "QUARANTINED_EDITORIAL"
    )
    result["can_publish"] = False
    result["reason"] = reason
    return result


def register_article(
    conn: sqlite3.Connection, *, article_id: int, run_id: int,
    topic: dict[str, Any], card: dict[str, Any], draft: dict[str, Any], status: str,
    commit: bool = True,
) -> int:
    mechanism = str(card.get("main_mechanism") or "").strip()
    conn.execute(
        "INSERT INTO content_items (article_id, run_id, kind, status, topic, title,"
        " mechanism, created_at) VALUES (?, ?, 'ARTICLE', ?, ?, ?, ?, ?)"
        " ON CONFLICT(article_id) DO UPDATE SET status=excluded.status,"
        " topic=excluded.topic, title=excluded.title, mechanism=excluded.mechanism",
        (article_id, run_id, status, topic.get("title"), draft.get("title"),
         mechanism, now()),
    )
    if commit:
        conn.commit()
    row = conn.execute(
        "SELECT id FROM content_items WHERE article_id = ?", (article_id,)
    ).fetchone()
    return int(row["id"])


def mark_published(
    conn: sqlite3.Connection, *, article_id: int, canonical_url: str | None,
    external_id: str | None = None, published_at: str | None = None,
) -> None:
    conn.execute(
        "UPDATE content_items SET status='PUBLISHED', canonical_url=?,"
        " external_id=COALESCE(?, external_id), published_at=? WHERE article_id=?",
        (canonical_url, external_id, published_at or now(), article_id),
    )
    conn.execute("UPDATE articles SET status='PUBLISHED' WHERE id=?", (article_id,))
    conn.commit()


def record_revision(
    conn: sqlite3.Connection, *, run_id: int, iteration: int,
    trigger: dict[str, Any], before: dict[str, Any], after: dict[str, Any] | None,
    status: str, remaining: dict[str, Any] | None = None,
    article_id: int | None = None,
    commit: bool = True,
) -> int:
    cur = conn.execute(
        "INSERT INTO article_revisions (article_id, run_id, created_at, iteration,"
        " trigger_json, before_json, after_json, status, remaining_json)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (article_id, run_id, now(), iteration, _json(trigger), _json(before),
         _json(after) if after is not None else None, status,
         _json(remaining) if remaining is not None else None),
    )
    if commit:
        conn.commit()
    return int(cur.lastrowid)


def defer_topic(
    conn: sqlite3.Connection, *, run_id: int, topic: dict[str, Any], reason: str,
    missing_piece: str, research: dict[str, Any] | None = None,
    retry_after: str | None = None,
) -> int:
    """ODŁÓŻ staje się stanem trwałym z powodem i zachowanym researchem."""
    identity = {
        "title": str(topic.get("title") or "").strip().lower(),
        "question": str(topic.get("question") or "").strip().lower(),
    }
    fingerprint = _fingerprint(identity)
    stamp = now()
    conn.execute(
        "INSERT INTO deferred_topics (fingerprint, run_id, created_at, updated_at,"
        " topic_json, reason, missing_piece, research_json, retry_after)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(fingerprint) DO UPDATE SET run_id=excluded.run_id,"
        " updated_at=excluded.updated_at, attempts=deferred_topics.attempts+1,"
        " topic_json=excluded.topic_json, reason=excluded.reason,"
        " missing_piece=excluded.missing_piece, research_json=excluded.research_json,"
        " retry_after=excluded.retry_after, status='WAITING'",
        (fingerprint, run_id, stamp, stamp, _json(topic), reason, missing_piece,
         _json(research or {}), retry_after),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM deferred_topics WHERE fingerprint=?", (fingerprint,)
    ).fetchone()
    return int(row["id"])


def deferred_for_scout(conn: sqlite3.Connection, limit: int = 8) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, topic_json, reason, missing_piece, attempts, updated_at"
        " FROM deferred_topics WHERE status='WAITING'"
        " AND (retry_after IS NULL OR retry_after <= ?)"
        " ORDER BY updated_at ASC LIMIT ?", (now(), limit),
    ).fetchall()
    result = []
    for row in rows:
        try:
            topic = json.loads(row["topic_json"])
        except (TypeError, ValueError):
            topic = {}
        result.append({
            "id": row["id"], "title": topic.get("title"),
            "question": topic.get("question"), "reason": row["reason"],
            "missing_piece": row["missing_piece"], "attempts": row["attempts"],
            "updated_at": row["updated_at"],
        })
    return result


def _horizon(age_hours: float | None) -> str:
    age = max(0.0, float(age_hours or 0.0))
    if age <= 3:
        return "1H"
    if age <= 72:
        return "24H"
    return "7D"


METRICS = ("views", "opens", "likes", "comments", "restacks", "signups", "subscribes")


def record_snapshot(
    conn: sqlite3.Connection, *, content_id: int, metrics: dict[str, Any],
    captured_at: str | None = None, age_hours: float | None = None,
    followers: int | None = None, subscribers: int | None = None,
) -> dict[str, Any]:
    captured_at = captured_at or now()
    if age_hours is None:
        row = conn.execute(
            "SELECT published_at FROM content_items WHERE id=?", (content_id,)
        ).fetchone()
        try:
            published = datetime.fromisoformat(str(row["published_at"])) if row and row["published_at"] else None
            captured = datetime.fromisoformat(captured_at)
            age_hours = (captured - published).total_seconds() / 3600 if published else None
        except ValueError:
            age_hours = None
    horizon = _horizon(age_hours)
    values = {key: _as_nonnegative_int(metrics.get(key)) for key in METRICS}
    conn.execute(
        "INSERT OR REPLACE INTO metric_snapshots (content_id, captured_at, horizon,"
        " age_hours, followers, subscribers, views, opens, likes, comments, restacks,"
        " signups, subscribes, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (content_id, captured_at, horizon, age_hours, followers, subscribers,
         *(values[key] for key in METRICS), _json(metrics)),
    )
    conn.commit()
    return relative_performance(conn, content_id=content_id, horizon=horizon,
                                current={**values, "followers": followers})


def _as_nonnegative_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def _percentile(value: float, baseline: list[float]) -> float | None:
    if not baseline:
        return None
    return round(100.0 * sum(1 for x in baseline if x <= value) / len(baseline), 1)


def relative_performance(
    conn: sqlite3.Connection, *, content_id: int, horizon: str,
    current: dict[str, Any],
) -> dict[str, Any]:
    row = conn.execute("SELECT kind FROM content_items WHERE id=?", (content_id,)).fetchone()
    if not row:
        raise ValueError(f"nie istnieje content_id={content_id}")
    baseline_rows = conn.execute(
        "SELECT s.* FROM metric_snapshots s JOIN content_items c ON c.id=s.content_id"
        " WHERE c.kind=? AND s.horizon=? AND s.content_id<>?"
        " AND s.id=(SELECT s2.id FROM metric_snapshots s2"
        "           WHERE s2.content_id=s.content_id AND s2.horizon=s.horizon"
        "           ORDER BY s2.captured_at DESC LIMIT 1)"
        " ORDER BY s.captured_at DESC LIMIT 30",
        (row["kind"], horizon, content_id),
    ).fetchall()
    result: dict[str, Any] = {
        "horizon": horizon, "baseline_n": len(baseline_rows),
        "confidence": confidence_for(len(baseline_rows)), "dimensions": {},
    }
    for metric in METRICS:
        value = current.get(metric)
        if value is None:
            continue
        baseline = [float(r[metric]) for r in baseline_rows if r[metric] is not None]
        dimension: dict[str, Any] = {
            "absolute": value,
            "percentile": _percentile(float(value), baseline),
            "baseline_n": len(baseline),
        }
        followers = current.get("followers")
        if followers and metric in {"views", "likes", "comments", "restacks", "signups", "subscribes"}:
            normalized = 1000.0 * float(value) / float(followers)
            normalized_baseline = [
                1000.0 * float(r[metric]) / float(r["followers"])
                for r in baseline_rows if r[metric] is not None and r["followers"]
            ]
            dimension["per_1000_followers"] = round(normalized, 3)
            dimension["normalized_percentile"] = _percentile(normalized, normalized_baseline)
            dimension["normalized_baseline_n"] = len(normalized_baseline)
        result["dimensions"][metric] = dimension
    return result


def record_signal(
    conn: sqlite3.Connection, *, kind: str, text: str = "", author: str = "",
    content_id: int | None = None, target_external_id: str | None = None,
    external_id: str | None = None, observed_at: str | None = None,
    raw: dict[str, Any] | None = None,
) -> int:
    external_id = external_id or _fingerprint({
        "target": target_external_id, "kind": kind, "text": text, "author": author,
    })
    conn.execute(
        "INSERT INTO audience_signals (content_id, target_external_id, external_id,"
        " observed_at, kind, text, author, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(external_id, kind) DO UPDATE SET"
        " content_id=COALESCE(excluded.content_id, audience_signals.content_id),"
        " text=COALESCE(NULLIF(excluded.text, ''), audience_signals.text),"
        " author=COALESCE(NULLIF(excluded.author, ''), audience_signals.author),"
        " raw_json=excluded.raw_json",
        (content_id, target_external_id, external_id, observed_at or now(), kind,
         text, author, _json(raw or {})),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM audience_signals WHERE external_id=? AND kind=?",
        (external_id, kind),
    ).fetchone()
    return int(row["id"])


def record_activity_event(conn: sqlite3.Connection, event: dict[str, Any]) -> int:
    """Zapisuje każdy typ zdarzenia; nieznany typ jest informacją, nie śmieciem."""
    raw_type = str(event.get("typ") or event.get("type") or "unknown").lower()
    if "reply" in raw_type or "comment" in raw_type:
        kind = "DISCUSSION"
    elif "question" in raw_type:
        kind = "CURIOSITY"
    elif "restack" in raw_type:
        kind = "RESTACK"
    elif "like" in raw_type:
        kind = "LIKE"
    else:
        kind = "OTHER"
    return record_signal(
        conn, kind=kind, target_external_id=str(event.get("czego") or "") or None,
        external_id=str(event.get("zdarzenie") or "") or None,
        observed_at=str(event.get("kiedy_zdarzenia") or "") or None,
        raw=event,
    )


def upsert_observation(
    conn: sqlite3.Connection, *, dimension: str, observation: str,
    evidence_count: int, topic: str = "", mechanism: str = "",
    evidence: list[Any] | None = None, status: str = "ACTIVE",
) -> str:
    memory_key = _fingerprint({
        "dimension": dimension, "observation": observation,
        "topic": topic, "mechanism": mechanism,
    })
    stamp = now()
    conn.execute(
        "INSERT INTO editorial_observations (memory_key, topic, mechanism, dimension,"
        " observation, evidence_count, confidence, first_seen_at, last_seen_at,"
        " status, evidence_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(memory_key) DO UPDATE SET evidence_count=excluded.evidence_count,"
        " confidence=excluded.confidence, last_seen_at=excluded.last_seen_at,"
        " status=excluded.status, evidence_json=excluded.evidence_json",
        (memory_key, topic, mechanism, dimension, observation, evidence_count,
         confidence_for(evidence_count), stamp, stamp, status, _json(evidence or [])),
    )
    conn.commit()
    return memory_key


def _terms(text: str) -> set[str]:
    stop = {"about", "after", "before", "from", "have", "into", "that", "the", "this", "with", "your"}
    return {w for w in re.findall(r"[a-z0-9]{4,}", (text or "").lower()) if w not in stop}


def memory_brief(
    conn: sqlite3.Connection, query: str = "", limit: int = 8,
) -> dict[str, Any]:
    """Oddaje mały brief, nie zrzut całej historii publikacji."""
    observations = conn.execute(
        "SELECT dimension, observation, topic, mechanism, evidence_count, confidence"
        " FROM editorial_observations WHERE status='ACTIVE'"
        " ORDER BY evidence_count DESC, last_seen_at DESC LIMIT 40"
    ).fetchall()
    query_terms = _terms(query)

    def relevance(row: sqlite3.Row) -> tuple[int, int]:
        haystack = " ".join(str(row[k] or "") for k in ("topic", "mechanism", "observation"))
        overlap = len(query_terms & _terms(haystack)) if query_terms else 0
        return overlap, int(row["evidence_count"] or 0)

    ordered = sorted(observations, key=relevance, reverse=True)
    if query_terms:
        related = [r for r in ordered if relevance(r)[0] > 0][:limit]
    else:
        related = ordered[:limit]

    signal_rows = conn.execute(
        "SELECT kind, text, observed_at FROM audience_signals"
        " WHERE kind IN ('CURIOSITY', 'DISAGREEMENT', 'CORRECTION', 'DISCUSSION')"
        " AND COALESCE(text, '')<>'' ORDER BY observed_at DESC LIMIT ?", (limit,),
    ).fetchall()
    content_count = int(conn.execute(
        "SELECT COUNT(*) FROM content_items WHERE status='PUBLISHED'"
    ).fetchone()[0])
    return {
        "published_content_n": content_count,
        "confidence": confidence_for(content_count),
        "observations": [dict(r) for r in related],
        "recent_reader_signals": [dict(r) for r in signal_rows],
        "deferred_topics": deferred_for_scout(conn, limit=min(5, limit)),
        "rules": [
            "Treat patterns as hypotheses, never automatic style changes.",
            "Keep reach, discussion, curiosity, disagreement and restacks separate.",
            "Do not repeat an argument merely because its raw likes were high.",
        ],
    }


def editorial_report(conn: sqlite3.Connection) -> dict[str, Any]:
    counts = {}
    for table in ("content_items", "metric_snapshots", "audience_signals",
                  "editorial_observations", "deferred_topics", "article_revisions"):
        counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    return {"counts": counts, "memory": memory_brief(conn)}

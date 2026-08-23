"""E-024: read-only live canary aktywnego `stages.fetch` na zatwierdzonych URL-ach.

Nie wywołuje modeli, przeglądarki ani Substacka. Utrwala pełny tekst, redirecty,
DNS pins, hashe i wiersze bazy w osobnym katalogu eksperymentu.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlparse

import capabilities
import db
import stages


OUTPUT = Path(".live-experiments/E-024-safe-fetch-canary")
SOURCES = (
    {
        "key": "doi_fy2024",
        "title": "DOI FY2024 Orphaned Wells Program annual report",
        "url": "https://www.doi.gov/sites/default/files/documents/2024-11/fy-2024-owpo-annual-congressional-reportfinal-publishing.pdf",
        "class": "PRIMARY",
        "evidence_role": "CURRENT_SCALE",
    },
    {
        "key": "blm_2024",
        "title": "BLM orphaned wells factsheet, June 2024",
        "url": "https://www.blm.gov/sites/default/files/docs/2024-06/BLM-OilandGas-Orphanwells-Factsheet-June2024.pdf",
        "class": "PRIMARY",
        "evidence_role": "CURRENT_SCALE",
    },
    {
        "key": "gao_2019",
        "title": "GAO-19-615 Oil and Gas: Bureau of Land Management Should Address Risks from Insufficient Bonds",
        "url": "https://www.gao.gov/products/gao-19-615",
        "class": "PRIMARY",
        "evidence_role": "CAUSAL_MECHANISM",
    },
    {
        "key": "osmre_aml",
        "title": "OSMRE Reclaiming Abandoned Mine Lands",
        "url": "https://www.osmre.gov/programs/reclaiming-abandoned-mine-lands",
        "class": "PRIMARY",
        "evidence_role": "SECOND_ACT",
    },
    {
        "key": "iogcc_2008",
        "title": "IOGCC Protecting Our Country's Resources",
        "url": "https://oklahoma.gov/content/dam/ok/en/iogcc/documents/publications/protecting_our_countrys_resources-the_states_case-2008.pdf",
        "class": "PRIMARY",
        "evidence_role": "CAUSAL_MECHANISM",
    },
    {
        "key": "capitol_forum",
        "title": "The Capitol Forum orphan well ownership investigation",
        "url": "https://thecapitolforum.com/early-bids-for-orphan-well-plugging-reveal-cracks-in-states-ability-to-accurately-track-well-ownership-active-operators-are-poised-to-further-exploit-state-processes-to-offload-retirement-ob/",
        "class": "SUPPORTING",
        "evidence_role": "COUNTEREVIDENCE",
    },
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _preflight() -> None:
    state = capabilities.status()
    if state["mode"] != "model_test" or state["kill_switch"]:
        raise RuntimeError(f"E-024 wymaga model_test i kill_switch=0: {state}")
    if OUTPUT.exists():
        raise RuntimeError(f"katalog E-024 już istnieje: {OUTPUT}")
    for source in SOURCES:
        host = (urlparse(source["url"]).hostname or "").lower()
        if host == "substack.com" or host.endswith(".substack.com"):
            raise RuntimeError("Substack jest bezwarunkowo zabroniony w E-024")


def main() -> int:
    _preflight()
    OUTPUT.mkdir(parents=True)
    conn = db.connect(OUTPUT / "experiment.db")
    run_id = db.start_run(conn, "fetch_canary")
    requested = [dict(source, host=urlparse(source["url"]).netloc) for source in SOURCES]
    status = "FAILED"
    error = ""
    fetched: list[dict] = []
    try:
        fetched = stages.fetch(conn, run_id, requested)
        status = "DONE"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        db.finish_run(conn, run_id, status, "fetch_canary", error)

    fetched_by_requested = {item["requested_url"]: item for item in fetched}
    rows = conn.execute(
        "SELECT url, domain, title, source_class, fetched_ok, fail_reason, "
        "requested_url, final_url, redirect_chain_json, resolved_ips_json, "
        "document_id, content_sha256 FROM sources ORDER BY id"
    ).fetchall()
    manifest_sources = []
    for source, row in zip(SOURCES, rows, strict=True):
        item = fetched_by_requested.get(source["url"])
        text = str(item.get("text") or "") if item else ""
        text_path = None
        if text:
            text_path = f"{source['key']}.txt"
            (OUTPUT / text_path).write_text(text, encoding="utf-8")
        manifest_sources.append({
            **source,
            "fetched_ok": bool(row["fetched_ok"]),
            "fail_reason": row["fail_reason"],
            "final_url": row["final_url"],
            "redirect_chain": json.loads(row["redirect_chain_json"]),
            "resolved_ips": json.loads(row["resolved_ips_json"]),
            "document_id": row["document_id"],
            "content_sha256": row["content_sha256"],
            "text_chars": len(text),
            "text_sha256_recomputed": _sha256(text) if text else None,
            "text_path": text_path,
        })

    manifest = {
        "experiment": "E-024",
        "mode": "model_test",
        "model_calls": 0,
        "api_cost_usd": 0.0,
        "substack_accesses": 0,
        "run_id": run_id,
        "status": status,
        "error": error or None,
        "requested_count": len(SOURCES),
        "fetched_count": len(fetched),
        "sources": manifest_sources,
    }
    (OUTPUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if status == "DONE" else 1


if __name__ == "__main__":
    raise SystemExit(main())

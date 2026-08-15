"""Wygodny skrót do uruchomienia przepływu tematów.

Użycie:
    python scripts/run_topics.py --count 6
Równoważne: python -m app.main run-topics --count 6
"""
from __future__ import annotations

import sys
from pathlib import Path

# Pozwala uruchomić skrypt bez instalacji pakietu (dodaje root projektu do sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["run-topics", *sys.argv[1:]]))

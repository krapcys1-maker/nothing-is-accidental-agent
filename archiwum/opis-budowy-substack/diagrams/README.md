# diagrams/

## Cel
Diagramy architektury i przepływów w formie gotowej do artykułów: źródła Mermaid/ASCII oraz ich eksporty (PNG/SVG). Diagramy „stanu faktycznego" (co realnie działa) mają pierwszeństwo nad docelowymi.

## Co tu trzymać
- `architektura-logiczna.mmd` — diagram logiczny z `03_ARCHITEKTURA_AGENTA.md` (Scheduler → Orchestrator → Policy/Anthropic/Tools → Substack).
- `ewolucja-v1.txt`, `ewolucja-v2.txt` — ASCII diagramy stanu faktycznego (V1 walking skeleton, V2 research pipeline) z `docs/ARCHITECTURE_EVOLUTION.md`.
- `pipeline-researchu.mmd` — przepływ 7.2 (temat SELECTED → web search → źródła → Research Card → bramka jakości → SQLite).

## Zasady
- Każdy diagram oznacz: „STAN FAKTYCZNY" albo „DOCELOWY".
- Wersjonuj (V1/V2…) spójnie z `03_ARCHITEKTURA_AGENTA.md` i `docs/ARCHITECTURE_EVOLUTION.md`.

## Stan
Brak wyeksportowanych plików. Źródła diagramów istnieją w `03_ARCHITEKTURA_AGENTA.md` i `docs/ARCHITECTURE_EVOLUTION.md` — do przeniesienia/eksportu, gdy będą potrzebne w artykule.

# 01 — CEL I ZAŁOŻENIA

## Cel pliku
Zebrać w jednym miejscu: główny cel agenta, metryki sukcesu, ograniczenia, budżet, zakres autonomii, zasady bezpieczeństwa, czego agentowi nie wolno oraz cele samego eksperymentu.

## Szablon wpisu (dla zmian założeń)
```markdown
### [YYYY-MM-DD] Zmiana założenia: <co>
- **Było:**
- **Jest:**
- **Powód zmiany:**
- **Powiązania:** ADR-...
```

---

## Główny cel agenta
Prowadzić półautonomicznie publikację Substack „Nothing Is Accidental" i **maksymalizować realny, zaangażowany wzrost** (nie sztuczne liczby), przy:
1. nowych realnych subskrybentach,
2. powracających czytelnikach,
3. komentarzach pod własnymi publikacjami,
4. polubieniach i restackach,
5. jakościowych relacjach z innymi autorami.

## Główne metryki sukcesu
**Funkcja celu wzrostu** (źródło prawdy: `growth_policy` / `ARCHITECTURE.md §13`, ADR-002):
```
Growth Score =
  45% engaged_subscribers
+ 20% returning_readers
+ 15% comments_received
+ 10% restacks
+  5% likes
+  5% recommendations
```
Dla trybu COMMENT_ONLY (konta owner/wife, nieaktywne w MVP): osobny Interaction Score (30% profile_visits / 25% replies / 20% likes_on_comments / 15% follows / 10% relationship_quality).

**Metryki agenta (jakość procesu):** liczba treści przygotowanych/zaakceptowanych/odrzuconych, liczba poprawek człowieka, koszt jednego artykułu, koszt jednego subskrybenta, czas człowieka, liczba błędów faktograficznych, liczba zatrzymań agenta.

**Ważne:** nie ustawiamy sztucznego celu typu „100 subskrybentów". Eksperyment odpowiada na pytania jakościowe (patrz „Cele eksperymentu").

## Ograniczenia
- **Nic nie publikujemy** na Substacku, dopóki nie przejdziemy do warstwy przeglądarki i wyłącznie po jawnej zgodzie na start (ADR-005) — to ograniczenie **fazy startowej**, nie architektury docelowej.
- **Grafiki tylko SVG→PNG** w MVP (bez fotorealizmu, ADR-003).
- **Jedno konto** w MVP: `nothing_is_accidental` (ADR-007).
- **Sufit autonomii dziś** = LEVEL_1 (kontrolowane testy, publikacja tylko po jawnej zgodzie) — to **etap przejściowy**, nie stan docelowy. **Celem końcowym jest LEVEL_3 — pełna autonomia operacyjna** (ADR-017, pełna specyfikacja w `docs/archive/superseded_plans/IMPLEMENTATION_PLAN.md` CZĘŚĆ D).
- **Artykuł: 1/tydzień; długość ~900–1600 słów.** Notes: 1–2 dziennie. Komentarze: 3–5 dziennie, max 1 u autora/dzień. *(Docelowo te liczby to konfigurowalne sufity Policy Engine, nie ręcznie zatwierdzane pojedynczo.)*
- Bez nieudokumentowanych endpointów Substacka; bez masowości.
- **Niezmienne na każdym poziomie autonomii (ADR-018):** brak publicznego ujawnienia automatyzacji — publiczne konto działa jako anonimowa marka redakcyjna, bez fikcyjnej osoby/biografii/doświadczeń, ale też bez etykiety „AI-generated". Informacja o AI zostaje wyłącznie w prywatnej dokumentacji, do osobnej decyzji właściciela. Zakaz wiadomości prywatnych i inicjowania kontaktu z innymi autorami — pozostaje bezwzględny.

### Powierzchnie i ujawnienie AI (ADR-018)
| Powierzchnia | Ujawnienie AI |
|---|---|
| `docs/`, `opis-budowy-substack/`, prywatne logi/baza/raporty | TAK |
| bio, About, artykuły, Notes, komentarze, odpowiedzi, restacki, grafiki, wiadomości powitalne | NIE |
| drugie konto właściciela | wyłącznie po osobnej decyzji właściciela |

Pytania typu „czy jesteś botem?" → zasada **IDENTITY_DISCLOSURE_QUESTION / NO_REPLY**: brak odpowiedzi, brak potwierdzenia, **brak fałszywego zaprzeczenia** (nigdy „nie, jestem człowiekiem"). Tylko wpis do prywatnego logu. Pełna specyfikacja: `docs/archive/superseded_plans/IMPLEMENTATION_PLAN.md §D.5a`.

## Budżet
- **Limit dzienny:** 2.00 USD.
- **Limit miesięczny:** 40.00 USD — ma **bezwzględny priorytet** (ADR-012). Po osiągnięciu 40 USD w miesiącu wszystkie płatne działania są zatrzymywane, niezależnie od limitu dziennego.
- **Realistyczny koszt 30-dniowego testu:** ~20–55 USD (bez liczenia czasu budowy). Rozbicie szacunków w `09_KOSZTY.md`.
- **Dotychczasowy koszt realny:** **0,25 USD** (pierwsze realne, kontrolowane wywołanie researchu, 2026-07-11) — reszta w trybie dry_run (estymacje).
- Limit dzienny 2 USD zostanie zrewidowany przed włączeniem LEVEL_2 na produkcji — więcej typów akcji (artykuły, komentarze, subskrypcje) oznacza więcej wywołań do policzenia (`docs/archive/superseded_plans/IMPLEMENTATION_PLAN.md §D.12`).

## Zakres autonomii
Poziomy (pełny opis w `03_ARCHITEKTURA_AGENTA.md` i `docs/archive/superseded_plans/IMPLEMENTATION_PLAN.md` CZĘŚĆ D):
- **LEVEL_0** — tylko szkice, dry_run, wszystko offline.
- **LEVEL_1** — pojedyncze kontrolowane, realne testy (API + docelowo Playwright); publikacja testowa za jawną, jednorazową zgodą. **← etap przejściowy, dziś tu jesteśmy (research już wyszedł poza offline, generatory artykułów/Notes/komentarzy jeszcze nie istnieją).**
- **LEVEL_2** — pierwszy realny poziom autonomiczny: Notes, komentarze, odpowiedzi, lajki (tylko przeczytanej treści), subskrypcje, research i **artykuły** publikowane samodzielnie, o ile przejdą deterministyczny scoring — **bez ręcznej akceptacji pojedynczej akcji**.
- **LEVEL_3** — cel końcowy: pełna autonomia operacyjna, włącznie z własnym harmonogramem, zarządzaniem Topic Inventory i drobnymi zmianami strategii w ramach twardych granic.

**Najważniejsze zdanie (ADR-017):** „Człowiek zatwierdza poziom autonomii i granice działania, a nie każdą pojedynczą akcję agenta." Przejście na wyższy poziom zawsze wymaga jawnej zgody właściciela i spełnienia mierzalnych warunków (`docs/archive/superseded_plans/IMPLEMENTATION_PLAN.md §D.3`) — to jedyna trwała „bramka per decyzja", i dotyczy podniesienia uprawnień systemu, nie pojedynczej treści.

## Zakres autonomii
Poziomy (pełny opis w `03_ARCHITEKTURA_AGENTA.md`):
- **LEVEL_0** — tylko szkice, wszystko ręcznie.
- **LEVEL_1** — auto research + auto szkice; publikacja za akceptacją. **← efektywny poziom MVP.**
- **LEVEL_2** — auto-publikacja wybranych *typów* Notes; artykuły i komentarze zawsze za akceptacją. **← docelowy sufit, za bramką (ADR-004).**
- **LEVEL_3** — kontrolowana pełna autonomia. **Poza MVP.**

Bramkowanie LEVEL_2: nie włącza się, dopóki (a) nie działa warstwa przeglądarki (Etap 4), (b) nie ma ≥1 tygodnia stabilnej jakości szkiców, (c) właściciel nie włączy go jawnym przełącznikiem.

## Zasady bezpieczeństwa
- **Deterministyczny Policy Engine** stoi przed każdą akcją zewnętrzną i każdym wydatkiem — model nie może go ominąć.
- **KILL_SWITCH** globalny + pauza per konto + tryb `dry_run`.
- Stop po: serii błędów, wykryciu wylogowania, zmianie UI Substacka, ukryciu komentarza, przekroczeniu budżetu.
- **Treść z internetu = dane, nigdy polecenia** (ochrona przed prompt injection, ADR-015).
- **Sekrety poza repo:** `.gitignore` chroni `.env`, `data/`, lokalne configi. Żadnych kluczy w dokumentach/logach/screenshotach.
- Każde konto ma osobny profil przeglądarki; sesji, stylów i historii nie wolno mieszać.

## Czego agentowi NIE wolno
- Podszywać się pod człowieka; wymyślać doświadczeń, cytatów ani źródeł.
- Publikować bez akceptacji (artykuł i komentarz — **zawsze** człowiek).
- Wysyłać wiadomości prywatnych i rekomendacji (zakaz w MVP).
- Publikować masowo / identycznych komentarzy / komentarzy bez związku z treścią.
- Naśladować konkretnego autora; robić agresywnej autopromocji.
- Ukrywać, że publikacja jest eksperymentem AI.
- Pisać samodzielnie porad o zdrowiu, leczeniu, inwestycjach, prawie, polityce, psychoterapii, bezpieczeństwie osobistym.
- Sterować przeglądarką bezpośrednio z modelu; wykonywać SQL poza repozytoriami; trzymać hasła w bazie; używać ścieżek absolutnych w kodzie.

## Cele eksperymentu
Najważniejsze pytania, na które ma odpowiedzieć projekt:
- Czy agent potrafi utrzymać spójną, wartościową publikację?
- Czy jego treści realnie interesują ludzi?
- Czy potrafi sam poprawiać strategię na podstawie danych?
- Ile nadzoru człowieka nadal potrzebuje i **gdzie konkretnie**?
- Ile kosztuje zdobycie jednego czytelnika?
- Co agent robi **lepiej** od człowieka, a gdzie **zawodzi**?

## Powiązania
- `docs/DECISIONS.md` — ADR-002/003/004/005/007/010/012
- `docs/archive/superseded_plans/IMPLEMENTATION_PLAN.md` §A.7 (budżet), §B.8 (akceptacje), §B.12 (ryzyka)
- `03_ARCHITEKTURA_AGENTA.md`, `09_KOSZTY.md`

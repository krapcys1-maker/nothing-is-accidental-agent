> **ARCHIVED — NOT A SOURCE OF TRUTH. DO NOT USE FOR IMPLEMENTATION.**
> Dokument historyczny (zarchiwizowany 2026-07-12). Obowiazuja wylacznie: MASTER_ARCHITECTURE.md, IMPLEMENTATION_ROADMAP.md, CURRENT_PROJECT_STATE.md (korzen repozytorium) oraz rejestr decyzji docs/DECISIONS.md.

# Architektura integracji z istniejącym kontem Substack

Status: **PROJEKT** (na obecnym etapie nie łączymy się z kontem — tylko opisujemy jak to zrobimy). Data: 2026-07-11.

## 1. Stan początkowy

- Konto Substack **już istnieje**.
- Nazwa profilu: **Nothing Is Accidental**
- Bio: *„Explaining the hidden systems, incentives and decisions behind ordinary things."*
- Język publikacji: **angielski**.
- `account_id` w systemie: `nothing_is_accidental`.

**Nie tworzymy nowego konta.** System ma się później połączyć z tym istniejącym kontem.

## 2. Ograniczenia bieżącego etapu (twarde)

Na teraz system:
- **nie publikuje** żadnej treści,
- **nie loguje się automatycznie**,
- **nie zapisuje hasła** ani danych logowania,
- przygotowuje **wyłącznie architekturę** integracji.

Te ograniczenia obowiązują do czasu jawnej zgody właściciela i dojścia do Etapu 4 (warstwa przeglądarki).

## 3. Model uwierzytelnienia

Substack używa logowania **magic-linkiem e-mail** (i/lub OAuth), zwykle **bez klasycznego hasła**. Konsekwencje:
- Nie ma hasła do przechowania → zasada „bez haseł" jest naturalnie spełniona.
- **Logowanie wykonuje człowiek ręcznie**, jednorazowo, w dedykowanym profilu przeglądarki. Agent nie obsługuje skrzynki e-mail ani nie klika magic-linku.
- Po zalogowaniu **sesja utrzymuje się w trwałym profilu Playwright** (cookies/localStorage w katalogu profilu) — kolejne uruchomienia nie wymagają ponownego logowania, dopóki sesja jest ważna.

## 4. Izolacja przez profil przeglądarki

- Każde konto ma **osobny persistent context Playwright** w `data/browser-profiles/<account_id>/`.
- Dla tego konta: `data/browser-profiles/nothing_is_accidental/`.
- Katalog `data/` jest **gitignored** — sesje i cookies nigdy nie trafiają do repo.
- Profil jednego konta nie jest współdzielony z żadnym innym (ochrona przed pomieszaniem kont, ryzyko R10).

## 5. Mapowanie na `BrowserPort`

Integracja realizowana jest wyłącznie przez `BrowserPort` (patrz `IMPLEMENTATION_PLAN.md §B.6`). Model językowy **nigdy** nie steruje przeglądarką bezpośrednio — proponuje akcję (`ProposedAction`), Policy Engine ją waliduje, orchestrator wywołuje port.

Zakres metod wg etapu:

| Metoda `BrowserPort` | Etap, w którym włączona | Uwaga |
|----------------------|-------------------------|-------|
| `is_logged_in(account_id)` | Etap 4 (najpierw) | wykrycie ważnej sesji; brak → notyfikacja, stop |
| `take_screenshot(account_id, label)` | Etap 4 | dowody do `SCREENSHOT_INDEX.md` |
| `open_feed / read_post / read_note / open_profile` | Etap 4 (read-only) | tylko odczyt, zero akcji zmieniających |
| `search_publications` | Etap 5 | discovery do komentarzy |
| `collect_metrics` | Etap 5 | tolerancyjnie na błędy; estymacje oznaczane |
| `create_article_draft` | Etap 4/5 | draft, **bez** publikacji |
| `publish_note / publish_comment / publish_article` | **Etap 4+ i tylko po jawnej zgodzie** | domyślnie zablokowane; `dry_run` |
| `like_item / restack_item` | Etap 5+ | za akceptacją |

## 6. Procedura pierwszego połączenia (gdy dojdziemy do Etapu 4)

1. System otwiera dedykowany profil Playwright dla `nothing_is_accidental` (widoczne okno, nie headless).
2. **Człowiek** loguje się ręcznie (magic-link/OAuth) w tym oknie.
3. System woła `is_logged_in()` i robi screenshot `login-success` (bez danych logowania w kadrze).
4. Sesja zostaje w profilu; system działa dalej **tylko w trybie odczytu**.
5. Publikacja pozostaje wyłączona do osobnej decyzji.
6. Wpis do `HUMAN_INTERVENTIONS.md` (typ LOGIN) + `BUILD_LOG.md`.

## 7. Wykrywanie problemów sesji (stop-conditions)

- Brak zalogowania / wygaśnięcie sesji → **stop akcji + notyfikacja** (nie próbujemy logować automatycznie).
- Wykryta zmiana UI Substacka (brak spodziewanych selektorów) → stop + wpis do `ERRORS_AND_FAILURES.md` (R2).
- Ukrycie/usunięcie komentarza po publikacji → cooldown/stop (R5).

## 8. Czego architektura celowo NIE robi

- Nie korzysta z nieudokumentowanych/prywatnych endpointów API Substacka.
- Nie automatyzuje logowania ani obsługi e-maila.
- Nie przechowuje żadnych danych logowania poza sesją w profilu przeglądarki (którą tworzy człowiek).
- Nie masowo działa — limity antyspamowe z `growth_policy` obowiązują.

## 9. Powiązania

- `IMPLEMENTATION_PLAN.md` §B.6 (BrowserPort), §B.7 (przepływ publikacji), §B.9 (wielokontowość), §B.12 (ryzyka R2/R3/R10/R11).
- `DECISIONS.md` ADR-005 (brak publikacji w MVP-0), ADR-011 (integracja z istniejącym kontem).

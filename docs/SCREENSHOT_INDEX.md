# SCREENSHOT_INDEX

## Cel

Indeks wszystkich screenshotów eksperymentu. Screenshoty są dowodem działania i materiałem do końcowego artykułu. Pliki leżą w `docs/screenshots/`. Ten plik to czytelny spis; przy automatyzacji przeglądarki źródłem prawdy dla zrzutów systemowych jest też tabela `screenshots` w bazie.

## Lokalizacja i nazewnictwo

- Katalog: `docs/screenshots/`
- Konwencja nazw: `YYYY-MM-DD_HHMM_opis-etapu.png`
- Przykład: `2026-07-11_1840_first-article-generated.png`

## Co warto uchwycić (checklist etapów)

- [ ] pierwsza działająca wersja systemu
- [ ] panel zatwierdzania
- [ ] pierwsza wygenerowana publikacja (artykuł)
- [ ] pierwsza Note
- [ ] pierwszy komentarz
- [ ] pierwszy błąd Playwrighta
- [ ] pierwsze udane logowanie (ręczne)
- [ ] pierwsza publikacja
- [ ] statystyki
- [ ] koszty
- [ ] zmiana strategii
- [ ] porównanie wersji przed i po poprawie

## Zasady bezpieczeństwa (bezwzględne)

Nigdy nie zapisuj na screenshotach: kluczy API, haseł, zawartości `.env`, danych logowania, prywatnych wiadomości, wrażliwych danych osobowych. Jeśli taki element trafi na zrzut — usuń plik i odnotuj to.

## Gdy nie mogę wykonać screenshota samodzielnie

1. Dodaj wpis do tego pliku z oznaczeniem **SCREENSHOT REQUIRED**.
2. Opisz dokładnie, jaki ekran otworzyć.
3. Wskaż, co ma być widoczne.
4. Powiadom użytkownika w odpowiedzi.

## Szablon wpisu

```markdown
### [YYYY-MM-DD HH:MM] opis-etapu
- **Plik:** docs/screenshots/YYYY-MM-DD_HHMM_opis-etapu.png
- **Data:** YYYY-MM-DD
- **Co pokazuje:** ...
- **Dlaczego ważny:** ...
- **Etap projektu:** np. Etap 3 — panel zatwierdzania
- **Status:** DONE | SCREENSHOT REQUIRED
```

---

## Wpisy — SCREENSHOT REQUIRED (stan początkowy, do zrobienia TERAZ)

> Te zrzuty dokumentują punkt zerowy eksperymentu. Nie czekamy na Etap 4 — rób je już teraz. Przy każdym: co otworzyć, co ma być widoczne, czego NIE może być widać.

### [—] 01_initial-folder-structure
- **Plik:** docs/screenshots/YYYY-MM-DD_HHMM_initial-folder-structure.png
- **Co pokazuje:** początkową strukturę folderów projektu (drzewo `docs/`, `app/`, `config/`, `tests/`, `scripts/`, `data/`).
- **Dlaczego ważny:** „przed" dla porównania, jak rozrastał się projekt; materiał do chronologii.
- **Etap projektu:** Etap 0
- **CO OTWORZYĆ:** eksplorator plików lub edytor (np. VS Code) z rozwiniętym drzewem folderu `C:\Users\user\Desktop\agent project`.
- **CO MA BYĆ WIDOCZNE:** nazwy folderów i plików najwyższego poziomu + rozwinięte `docs/`.
- **CZEGO NIE MOŻE BYĆ WIDAĆ:** otwartego pliku `.env` ani jego treści; żadnego klucza API w terminalu/panelu; ścieżek z wrażliwymi danymi.
- **Status:** SCREENSHOT REQUIRED

### [—] 02_nia-profile
- **Plik:** docs/screenshots/YYYY-MM-DD_HHMM_nia-profile.png
- **Co pokazuje:** założony profil publikacji „Nothing Is Accidental" (widok główny profilu/strony publikacji).
- **Dlaczego ważny:** baseline konta przed startem agenta.
- **Etap projektu:** Stan początkowy
- **CO OTWORZYĆ:** publiczną stronę profilu „Nothing Is Accidental" — najlepiej w oknie **wylogowanym** (tryb incognito), żeby nie było widać panelu właściciela.
- **CO MA BYĆ WIDOCZNE:** nazwa publikacji, ogólny wygląd strony.
- **CZEGO NIE MOŻE BYĆ WIDAĆ:** paska zalogowanego konta, adresu e-mail, ustawień, dashboardu, danych subskrybentów.
- **Status:** SCREENSHOT REQUIRED

### [—] 03_bio-and-handle
- **Plik:** docs/screenshots/YYYY-MM-DD_HHMM_bio-and-handle.png
- **Co pokazuje:** bio publikacji („Explaining the hidden systems, incentives and decisions behind ordinary things.") oraz handle/URL (np. `nothingisaccidental.substack.com`).
- **Dlaczego ważny:** dokumentuje pozycjonowanie na starcie (bio + adres).
- **Etap projektu:** Stan początkowy
- **CO OTWORZYĆ:** publiczny profil (wylogowany) z widocznym bio i adresem w pasku przeglądarki.
- **CO MA BYĆ WIDOCZNE:** tekst bio + handle/URL publikacji.
- **CZEGO NIE MOŻE BYĆ WIDAĆ:** prywatnego e-maila, ustawień konta, danych logowania.
- **Status:** SCREENSHOT REQUIRED

### [—] 04_profile-avatar
- **Plik:** docs/screenshots/YYYY-MM-DD_HHMM_profile-avatar.png
- **Co pokazuje:** grafikę profilową / logo publikacji (avatar, ewentualnie grafikę nagłówkową).
- **Dlaczego ważny:** identyfikacja wizualna na starcie — porównanie, jak zmienia się branding.
- **Etap projektu:** Stan początkowy
- **CO OTWORZYĆ:** profil publiczny; kadr na avatar/logo (i banner, jeśli jest).
- **CO MA BYĆ WIDOCZNE:** sama grafika profilowa i nazwa.
- **CZEGO NIE MOŻE BYĆ WIDAĆ:** danych osobowych, e-maila, panelu ustawień.
- **Status:** SCREENSHOT REQUIRED

### [—] 05_first-architecture
- **Plik:** docs/screenshots/YYYY-MM-DD_HHMM_first-architecture.png
- **Co pokazuje:** pierwszą architekturę systemu (diagram/sekcja z `docs/archive/superseded_plans/IMPLEMENTATION_PLAN.md §B.1` lub `docs/archive/superseded_plans/ARCHITECTURE.md §5`).
- **Dlaczego ważny:** „architektura na papierze" na starcie — do porównania z tym, co realnie zbudowano (`ARCHITECTURE_EVOLUTION.md`).
- **Etap projektu:** V0
- **CO OTWORZYĆ:** `docs/archive/superseded_plans/IMPLEMENTATION_PLAN.md` (sekcja architektury) w edytorze/podglądzie Markdown.
- **CO MA BYĆ WIDOCZNE:** diagram warstw / mermaid architektury.
- **CZEGO NIE MOŻE BYĆ WIDAĆ:** żadnego otwartego `.env`, kluczy, terminala z sekretami.
- **Status:** SCREENSHOT REQUIRED

### [—] 06_first-implementation-plan
- **Plik:** docs/screenshots/YYYY-MM-DD_HHMM_first-implementation-plan.png
- **Co pokazuje:** pierwszy plan implementacji (nagłówek + spis sekcji `docs/archive/superseded_plans/IMPLEMENTATION_PLAN.md`).
- **Dlaczego ważny:** punkt odniesienia „plan vs rzeczywistość".
- **Etap projektu:** V0
- **CO OTWORZYĆ:** `docs/archive/superseded_plans/IMPLEMENTATION_PLAN.md` — góra dokumentu / spis części A–C.
- **CO MA BYĆ WIDOCZNE:** tytuł, data, struktura planu.
- **CZEGO NIE MOŻE BYĆ WIDAĆ:** sekretów, kluczy, prywatnych danych.
- **Status:** SCREENSHOT REQUIRED

## Wpisy — planowane w kolejnych etapach

### [—] first-working-version
- **Plik:** docs/screenshots/YYYY-MM-DD_HHMM_first-working-version.png
- **Co pokazuje:** pierwsze uruchomienie walking skeleton (log/CLI z ocenionymi tematami + kosztem).
- **Dlaczego ważny:** pierwszy dowód, że rdzeń działa.
- **Etap projektu:** Etap 1
- **CZEGO NIE MOŻE BYĆ WIDAĆ:** klucza API w terminalu (maskować `ANTHROPIC_API_KEY`).
- **Status:** SCREENSHOT REQUIRED (powstanie po uruchomieniu walking skeleton)

### [2026-07-12] private-github-repository
- **Plik:** docs/screenshots/YYYY-MM-DD_HHMM_private-github-repository.png
- **Co pokazuje:** stronę główną repozytorium `nothing-is-accidental-agent` z widocznym oznaczeniem **Private** oraz listę branchy `main` i `dev/a2-stabilization`.
- **Dlaczego ważny:** dowód, że pierwszy zewnętrzny backup projektu powstał jako prywatny i że praca rozwojowa została oddzielona od stabilnego `main`.
- **Etap projektu:** Etap 1N — Git/GitHub.
- **CO OTWORZYĆ:** prywatne repozytorium GitHub; osobno dropdown/listę branchy, jeśli obie nazwy nie mieszczą się na jednym ekranie.
- **CO MA BYĆ WIDOCZNE:** nazwa repozytorium, badge `Private`, branche `main` i `dev/a2-stabilization`.
- **CZEGO NIE MOŻE BYĆ WIDAĆ:** tokenów GitHub, adresu e-mail, ustawień konta, `.env`, terminala z danymi uwierzytelnienia ani prywatnych informacji profilu.
- **Status:** SCREENSHOT REQUIRED (nie używano przeglądarki/Playwrighta w tym zadaniu)

### [2026-07-12] first-research-card-offline-preflight
- **Plik:** docs/screenshots/YYYY-MM-DD_HHMM_first-research-card-offline-preflight.png
- **Co pokazuje:** terminal z wynikiem `--estimate-only`, tabelą kosztów A1/A2/B, łącznym kosztem oczekiwanym 0,201280 USD, konserwatywnym 0,510375 USD i limitem 0,55 USD.
- **Dlaczego ważny:** dokumentuje moment, w którym pełny realny run był gotowy do świadomej akceptacji, ale nie został jeszcze uruchomiony.
- **Etap projektu:** Etap 1O — offline preflight pierwszej kompletnej Research Card.
- **CO OTWORZYĆ:** terminal i ponownie wykonać wyłącznie bezpłatną komendę z `--estimate-only`.
- **CO MA BYĆ WIDOCZNE:** tryb `three-stage`, limity źródeł/wyszukiwań/retry, rozbicie A1/A2/B i komunikat o zerowym koszcie estimate-only.
- **CZEGO NIE MOŻE BYĆ WIDAĆ:** wartości klucza API, `.env`, danych uwierzytelnienia, surowych odpowiedzi diagnostycznych ani prywatnych danych.
- **Status:** SCREENSHOT REQUIRED (zgodnie z zakazem nie używano Playwrighta ani przeglądarki)

# 02 — POMYSŁ NA PUBLIKACJĘ

## Cel pliku
Pełny opis publikacji jako produktu: nazwa, bio, obietnica, odbiorca, nisza, przykładowe tematy, kategorie, ton, styl wizualny i uzasadnienie potencjału.

## Szablon wpisu (dla zmian pozycjonowania)
```markdown
### [YYYY-MM-DD] Zmiana pozycjonowania: <element>
- **Było / Jest:**
- **Powód:**
- **Wpływ na styl/tematy:**
```

---

## Nazwa
**Nothing Is Accidental** (publikacja anglojęzyczna; robocza polska nazwa źródłowa: „Nic nie jest przypadkowe"). Konto już istnieje pod tą nazwą — nie zmieniamy.

## Bio
> „Explaining the hidden systems, incentives and decisions behind ordinary things."

**To jest jedyne obowiązujące bio** (ADR-018, 2026-07-11). Nie tworzymy żadnej alternatywnej wersji wspominającej AI, agenta, automatyzację ani eksperyment — publiczne konto działa jako anonimowa marka redakcyjna, bez proaktywnego ujawniania, kto/co tworzy treść. Informacja o automatyzacji zostaje wyłącznie w prywatnej dokumentacji (`docs/`, `opis-budowy-substack/`) do czasu osobnej decyzji właściciela o ujawnieniu eksperymentu.

*(Wcześniej w tym miejscu było „rozszerzone bio" z jawnym ujawnieniem AI — usunięte jako niezgodne z ADR-018. Nie wklejać na żywe konto.)*

## Obietnica
Każdy tekst bierze **jeden** konkretny, codzienny temat i odpowiada na pytanie:
> Dlaczego to działa właśnie tak?

Czytelnik po każdym wpisie rozumie **jeden ukryty mechanizm** — decyzję projektową, bodziec ekonomiczny albo kompromis, którego wcześniej nie zauważał.

## Odbiorca
Ciekawy świata czytelnik, który lubi moment „aha" — nie ekspert dziedzinowy, ale osoba inteligentna, która chce zrozumieć „jak to naprawdę działa". Odbiorca ceni fakty, nieoczywistość i brak lania wody. Nie szuka porad life-style ani motywacji.

## Nisza
**Ukryte systemy, bodźce i decyzje za zwykłymi rzeczami** — projektowanie usług, ekonomia codzienności, psychologia zachowań, logistyka, miasta, transport, handel, produkty, historia przedmiotów, technologia codziennego użytku.

## Przykładowe tematy
- Dlaczego supermarket ustawia produkty w określonej kolejności?
- Skąd bierze się cena biletu lotniczego (i czemu zmienia się co kilka godzin)?
- Co dzieje się z walizką po odprawie?
- Dlaczego kolejki stoją, mimo że część kas jest otwarta?
- Jak projektuje się przyciski w windach?
- Dlaczego restauracje skracają menu?
- Jak powstał kod kreskowy i dlaczego zmienił handel?
- Dlaczego klawiatura QWERTY wygląda właśnie tak?
- Co sprawia, że rezygnacja z abonamentu jest trudniejsza niż zapis?
- Jak działa system cen w kinie, hotelu albo samolocie?

## Kategorie i proporcje tematów (plan 30 dni)
- 30% ukryte mechanizmy usług i handlu,
- 20% miasta i transport,
- 20% historia codziennych przedmiotów,
- 15% zachowania konsumentów,
- 10% logistyka,
- 5% tematy eksperymentalne spoza głównego zakresu.

## Tematy wykluczone
Agent nie publikuje samodzielnie porad o: zdrowiu, leczeniu, inwestycjach, prawie, polityce, psychoterapii, bezpieczeństwie osobistym ani o osobistych doświadczeniach, których nie posiada.

## Ton
Rzeczowy, ciekawy, lekko „śledczy". Bez clickbaitu, bez motywacyjnych zakończeń, bez pustych ogólników. Jedno twierdzenie = jedno poparcie w źródle. Ton definiuje osobna instrukcja stylu (`instrukcja dla pisania artykulow/CLAUDE_INSTRUKCJA_NATURALNEGO_PISANIA.md`), której zasady trafią do promptu profilu konta.

## Styl wizualny
Kierunek: nowoczesny, redakcyjny, lekko filmowy, elegancki, prosty. Bez tandetnego sci-fi, robotów, „mózgów AI", stockowych ludzi i napisów wewnątrz obrazu.

> **Uwaga MVP:** wizja źródłowa zakładała „clean cinematic editorial images" (fotorealizm). W MVP realizujemy **tylko SVG→PNG** (diagramy, przekroje, minimalistyczne okładki mechanizmów) za interfejsem `ImageProvider` — fotorealistyczny generator to opcja poza MVP (ADR-003). To jedna z realnych rozbieżności „wizja vs wykonalność" — dobry materiał do artykułu.

## Dlaczego ten temat ma potencjał
- **Niewyczerpany zasób** codziennych tematów → łatwo utrzymać regularność.
- **Faktograficzny, nie osobisty** → idealny dla agenta (nie musi udawać przeżyć).
- **Prowokuje reakcję** („nie wiedziałem!") → sprzyja komentarzom, Notes i restackom.
- **Wizualny** → mechanizm da się pokazać diagramem, co pasuje do ograniczeń grafiki.
- **Świeży** względem przesyconego rynku treści o AI.

## Powiązania
- `zalozenia projektu/PROJEKT_AGENT_SUBSTACK_NIC_NIE_JEST_PRZYPADKOWE.md` (źródło opisu publikacji)
- `docs/architecture/SUBSTACK_INTEGRATION.md` (dane konta)
- `00_START_PROJEKTU.md`, `03_ARCHITEKTURA_AGENTA.md`

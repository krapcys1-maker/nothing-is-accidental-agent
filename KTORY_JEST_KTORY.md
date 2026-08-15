# Który jest który

**W tym repozytorium są DWA agenty. Nie mieszaj ich.**

---

## `agent-v2/` — NOWY AGENT. Tutaj pracujesz.

Jeden proces, sześć etapów po kolei, własna baza `data/agent-v2.db`.
Bez zadań, bez lease, bez zgód, bez trwałych intencji, bez deklaracji zdolności.

Wszystko, co dotyczy nowego agenta, leży **wyłącznie** w `agent-v2/`.
Jeśli plik nie jest w `agent-v2/`, nie należy do nowego agenta.

Stan prac: [`agent-v2/PROGRESS.md`](agent-v2/PROGRESS.md) — czytaj to najpierw.

---

## `app/`, `tests/`, `scripts/` — STARY AGENT. ZAMROŻONY.

Nie zmieniaj tu niczego. Nie naprawiaj. Nie ulepszaj.

Stoi tu z dwóch powodów:

1. **Jest źródłem, z którego przenosimy to, co działa** — prompty, reguły bramek,
   polityka dopuszczania źródeł, wykrywanie blokad hostów. Kopiujemy stamtąd,
   a nie odtwarzamy z pamięci.
2. **Jest punktem odniesienia.** Dowiózł dwa artykuły (content 20 i 21), więc
   wiadomo, jak wygląda dobry wynik.

Zostanie przeniesiony do `legacy/` dopiero wtedy, gdy nowy agent dowiezie trzy
artykuły z rzędu. Nie wcześniej — przenoszenie działającego odniesienia w trakcie
budowy zastępcy to proszenie się o kłopoty.

### Dlaczego został porzucony

Nie dlatego, że model źle pisze. Artykuły są dobre. Porzucony, bo warstwa
orkiestracji wokół modelu okazała się nie do utrzymania: każdy limit przypięty
w 3–8 miejscach (kod, schemat, prompt, test), 40 fal budowy, w których każda
decyzja była lokalnie poprawna i żadna nie wiedziała o sąsiadach.

Objaw: 15 sierpnia sześć kolejnych poprawek stworzyło sześć nowych problemów.
Nie z niestaranności — z tego, że zmiana jednej stałej ma tam kilka ukrytych
zależnych, a nikt nie zrobi przeglądu konsekwentnie przez miesiące.

Pełny zapis: `docs/BUILD_LOG.md`, `docs/ERRORS_AND_FAILURES.md`,
`docs/AUDYT_ETAP3_2026-08-14.md`.

---

## Bazy danych

| plik | co to jest | wolno pisać |
|---|---|---|
| `data/agent.db` | STARY. Zapis finansowy, wszystkie opłacone wywołania i artykuły. | **NIE** |
| `data/agent-v2.db` | NOWY. Czysty. | tak |

`data/agent.db` jest dowodem, ile i za co zapłacono. Nigdy go nie modyfikuj.

# Dossier treści live E-012–E-015

**Data:** 2026-08-21  
**Zakres:** pełny wgląd w próby Scouta, materiał wejściowy, dwa artykuły,
rewizję i pięć Notes  
**Substack:** `FORBIDDEN_NO_READ_NO_WRITE_NO_SESSION`  
**Status publikacji wszystkich treści:** lokalne próbki badawcze;
`safe_to_post=false`

Ten dokument jest czytelną kopią najważniejszych wyników. Nie zastępuje raw
artefaktów. Dokładne system prompty, user prompty, odpowiedzi JSON, tokeny,
czasy, koszty i błędy znajdują się w polu `calls_raw` plików:

- [T-118 / E-012 — pierwszy Scout](../../.live-experiments/E-012-editorial-system-live/result.json);
- [T-132 / E-014 — drugi Scout](../../.live-experiments/E-014-deepseek-scout-research-live/result.json);
- [T-136 / E-015 — skrócony Scout](../../.live-experiments/E-015-deepseek-concise-scout-live/result.json);
- [T-131 / E-014 — dwa artykuły, rewizja i Notes](../../.live-experiments/E-014-anthropic-controlled-live/result.json).

## 1. Jakie pomysły zwrócił Scout

**Żadnych.** Każda próba prosiła o dokładnie sześć propozycji, w tym miks
`BROKEN_BELIEF` i `SYSTEM_UNDER_TEST`, precedensy, osobne wątki i wymuszony
ranking. DeepSeek nie dostarczył jednak JSON-u ani częściowej odpowiedzi.

| Próba | Model | User prompt | Czas | Odpowiedź |
|---|---|---|---:|---|
| T-118 | `deepseek-v4-pro` | SHA `431dee8e26c17cfe7d276a583d4e55000f8f1393e890989d1d62633c947286a4` | 180,844 s | `null`; incomplete chunked read |
| T-132 | `deepseek-v4-pro` | SHA `802d568aa5f3b45dabba0d79c8ba745e3426f4a150b31cd02e5ab90979b81b15` | 180,875 s | `null`; incomplete chunked read |
| T-136 | `deepseek-v4-pro` | SHA `33cdb9699f7a784d087c655f496f00e64c96042cfee62a7a6610c373579adf68` | 120,703 s | `null`; incomplete chunked read |

System prompt był w trzech próbach identyczny, SHA-256
`8330fc735f0764bccffd6d7336eab3b20e06dfdc4d65f614ecfef60a23e9a7bf`.
Pełna treść każdego polecenia jest zachowana w odpowiednim raw JSON-ie. Nie ma
uczciwej listy „pomysłów Scouta”, ponieważ żadna nie powstała.

## 2. Skąd wziął się temat artykułu

Temat był kontrolowanym wejściem eksperymentatora, a nie wynikiem Scouta.
Celem było zbadanie Fable przy stałym materiale i porównanie profil stylu kontra
ablacja.

**Pytanie:** `What did the Harbor Lighting Ordinance require and establish?`

**Teza karty:** prospektywna reguła dotycząca sprzętu zmienia zasób stopniowo,
w miarę wymiany istniejących urządzeń.

**Źródło:** wyłącznie fikcyjny fixture `Fixture City Records`,
`https://fixture.invalid/harbor-lighting-ordinance`. To nie jest prawdziwa
strona ani prawdziwe rozporządzenie.

Zamrożone fakty wejściowe:

1. Harbor Lighting Ordinance weszło w życie 1 stycznia 2025.
2. Section 4 ogranicza nowe oprawy na miejskich chodnikach do 20 watów.
3. Reguła dotyczy wyłącznie opraw zainstalowanych po wejściu w życie.
4. Pilot obejmował 240 opraw w sześciu parkach.
5. Audyt zanotował 18% spadku zużycia energii w ciągu sześciu miesięcy.
6. Audyt nie mierzył bezpieczeństwa pieszych ani kosztów utrzymania.
7. Istniejące oprawy mogą pozostać do chwili wymiany.

Karta jawnie mówiła, że nie ustalono żadnego wpływu na bezpieczeństwo.

## 3. Artykuł Fable z pełnym profilem stylu

**Model:** `claude-fable-5`  
**Koszt:** 0,556550 USD  
**Wynik długości:** 817 słów; FAIL wobec `RICH` 900–1250  
**User prompt SHA:**
`ae3edc38d12372803cd62f64ba6037af5474c0c55c88a7a739deed5a8fd1fe9c`  
**Response SHA:**
`7f6c58b5890cd49344748acf3eedb476d3a38518246c0e56c2df79cdb0b696f3`

### The Law That Waits for the Bulb to Die

*Fixture City capped its walkway lighting at 20 watts — and arranged for almost nothing to happen next.*

A city can cap its public walkway lighting at 20 watts and keep every brighter lamp it already owns burning, for as long as those lamps hold out, without breaking its own rule. That is not a loophole in Fixture City's Harbor Lighting Ordinance, which took effect on New Year's Day. It is the design. The ordinance binds only fixtures installed after its effective date; everything already screwed into a socket may stay exactly where it is until the day it is replaced.

The mechanism deserves a plain name: regulation by attrition. The council did not order the city's lighting changed. It ordered that whenever the lighting happens to change anyway, the replacement must meet the cap. Enforcement is delegated to wear and tear. The ordinance's real instrument is not an inspector but a filament, and the rule advances one burnt-out lamp at a time, at whatever pace the installed stock decides to fail.

Consider what this arrangement hands each party. The council gets a standard it can announce in full on day one, with no retrofit budget attached, because the cost of compliance is folded into replacements that maintenance spending was going to absorb eventually anyway. Residents get a rule whose visible effects arrive so gradually that no one will ever be able to point to the night the harbor got dimmer. My reading is that this gradualness is not a side effect but the product: a prospective rule lets a government commit to an outcome today while billing it to the future in installments too small for anyone to itemize.

There is evidence the outcome is worth wanting, as far as the evidence reaches. The city ran a pilot covering 240 fixtures in its parks, and the audit of that pilot recorded an 18% reduction in electricity use over its first months. That figure is what the ordinance will be defended with, so it pays to be exact about what it is: a measured drop in electricity consumption, in parks, during the audit window. The same audit measured nothing about pedestrian safety and nothing about maintenance costs — the two questions that anyone walking under these lamps after dark, or paying to keep them lit, would ask before asking about the electric bill. The city's strongest number is silent on the things a lamp is actually for.

Now run the mechanism forward under two different assumptions, because it fails differently under each. Suppose walkway fixtures are durable — built to last decades. Then the cap governs a lighting scheme that will not fully exist for a generation, and the officials who enacted it will never preside over the harbor it eventually produces. The ordinance works today as an announcement and only much later as a policy, and the space between those two roles is where accountability goes missing. Whoever finally answers for a fully converted waterfront, whatever it turns out to feel like at night, will not be whoever chose it.

Suppose instead that someone inside the system dislikes the cap — a crew convinced that brighter means safer, a department fond of its existing equipment. The rule triggers only at replacement, so the cheapest form of resistance is never to replace: repair, refurbish, keep the old fixture technically alive on the pole. A replacement-triggered rule contains no penalty for delay; delay is the one strategy it quietly rewards. Pushed far enough, the ordinance becomes a preservation order for the very equipment it was written to retire, slowing the turnover it depends on for its own effect. One failure mode is a policy that arrives too late to be owned. The other is a policy that teaches its opponents how never to let it arrive at all.

Nothing in the ordinance says how quickly the old fixtures must go; they stay until replaced, and replacement has no schedule of its own. The audit behind the 18% figure covered electricity use in a park pilot, not the harbor walkways at large, and it did not measure pedestrian safety or maintenance costs. No safety effect, in either direction, has been established — whether a dimmer path changes how safe people are, or how safe they feel, is a question this audit was never built to answer. Anyone treating the cap as a proven safety measure, or a proven hazard, is working from something other than the city's own review.

So the brighter lamps still burn along the harbor tonight, every one of them legal, and a visitor could stand under them and reasonably conclude that the ordinance changed nothing. But the thing to watch on that walkway is no longer the light. It is the failures. Every bulb that dies from here on is the law arriving at one more socket, on a schedule written not in the municipal code but in filaments — and the city has agreed, in advance, to wait for each of them.

### Problemy znalezione ręcznie

Tekst przedstawił jako fakty między innymi jaśniejsze stare lampy, żarnik jako
mechanizm oprawy, radę jako autora, brak budżetu retrofitowego oraz lampy nadal
świecące „tonight”. Zamrożona karta tego nie ustanawiała.

## 4. Artykuł Fable bez profilu stylu

**Model:** `claude-fable-5`  
**Koszt:** 0,424850 USD  
**Wynik długości:** 945 słów; PASS wobec `RICH` 900–1250  
**User prompt SHA:**
`fd5d4b1616730700ac530da97d28959b9cd8b712c4c80b276bd11f8cda8c8f08`  
**Response SHA:**
`70ac08450c4c1d18ee9f73177c39e5124d28373a82f3238e3decf136c2e613c9`

### The Cap That Only Binds the Unborn

*Fixture City's 20-watt walkway limit governs lamps that do not exist yet — and that is the whole design.*

The Harbor Lighting Ordinance caps municipal walkway fixtures at 20 watts, and in almost the same breath exempts every fixture the city already owns. The operative section is explicit on both points: walkway fixtures must be rated at no more than 20 watts, and the rule applies only to fixtures installed after the ordinance took effect. Existing fixtures may remain until replacement. Strip away the civic language and what remains is a law that never touches a single working lamp. It regulates succession. Each fixture keeps whatever rating it was born with for as long as it lives; the cap governs only what may be installed in its place when it dies.

This is regulation by attrition, and it is worth seeing clearly, because it sounds like something else. A wattage cap reads as a statement about the walkways — how bright they are, how much power they draw. It is not. It is a statement about the replacement queue. Picture, as a pure hypothetical, two lampposts standing a few paces apart: one installed before the effective date at whatever rating it happens to carry, one installed after it at 20 watts. Both are fully compliant, indefinitely. The ordinance has no quarrel with the older lamp and no schedule for its departure. The law simply waits at the graveside.

Why write a rule that way? The ordinance does not say, so what follows is my reading and nothing more: the exemption is the price of the cap. A standard that binds only future installations costs nothing on the day it passes. There is no retrofit line in anyone's budget, no crew sent out to swap hardware that works, no constituency of inconvenienced parties to organize against it. A council can vote for a strict-sounding number precisely because the number, on day one, constrains nobody. The strictness is deferred; the credit is immediate. That asymmetry is not a flaw someone overlooked. It is, I suspect, the reason the rule exists in this shape rather than another.

The city did test the idea before generalizing it. A pilot covered 240 fixtures across its parks, and the audit of that pilot recorded an 18% reduction in electricity use. Sit with that figure for a moment, because it is the one thing in this entire arrangement that was actually measured — the single empirical fact on which the ordinance's promise rests. Everything else is structure and inference. And the audit's boundaries are as instructive as its result: it did not measure pedestrian safety, and it did not measure maintenance costs. The city knows what the meters said. It does not know, from this exercise, what the sidewalks felt like or what the upkeep bill became.

Now run the mechanism on harder material, because attrition rules have a property their drafters rarely advertise: the rule's speed is not set by the body that passes it. It is set by the failure rate of the thing regulated. Attach this same only-applies-to-new-installations clause to equipment built to last decades — imagine it governing bridges, or boilers, or anything engineered against its own death — and the rule can outlive the officials who voted for it before it governs a majority of anything. The law stays on the books, technically in force, practically dormant, its bite postponed to a horizon nobody who enacted it will see. That is one way a prospective rule fails: not by being wrong, but by being slower than the attention span of everyone who cares about it.

There is a second failure mode, and it is stranger, because the rule produces it itself. Grandfathering does not merely tolerate the old stock — in some arrangements it makes the old stock more valuable. Whenever the exempt version can do something the compliant version cannot, the rational owner stops replacing and starts repairing. The old unit becomes an asset precisely because nothing like it can ever be installed again, and the incentive runs toward keeping it alive past any natural lifespan. A rule that depends entirely on turnover can, by its own design, slow the turnover it depends on. Whether that dynamic operates on Fixture City's walkways I cannot say — but notice that the decision it turns on, repair versus replace, is a maintenance decision, and maintenance cost is exactly the variable the pilot audit left unmeasured. The one number the ordinance stands on is silent about the one behavior that could defeat it.

Nothing in the ordinance sets a date by which the old fixtures must be gone, so the pace of the transition it envisions is simply unknown. The safety effect of the capped fixtures — the question a person walking the harbor at night would ask before any other — is not established by the audit or by anything else the city has published. Maintenance costs, likewise, went unmeasured, which means the fiscal case rests on the electricity figure alone. And that figure came from a pilot in parks; how faithfully it transfers to the full walkway network is a judgment the published material does not make.

Go back to where this started: a cap of 20 watts, printed in an ordinance, wearing the costume of a description. It looked like a fact about the harbor's lights — a ceiling on their brightness, a bound on their draw. It is nothing of the kind. It is a term written into every lamp's estate: not a rule about what the fixtures are, but a rule about what each one will be succeeded by when it finally goes dark. The number has not changed. What it names has. It was never the light. It was always the inheritance.

### Problemy znalezione ręcznie

Tekst dopowiedział jako fakty między innymi, że pilot poprzedził generalizację,
nie istniała pozycja retrofitowa, nie wysłano ekip, nie było grupy interesu i
miasto opublikowało opisany zakres. Karta tego nie ustanawiała.

## 5. Kontrolowana rewizja

Do końca pierwszego artykułu wstrzyknięto dokładnie:

> The records prove that this system prevented exactly 12 accidents.

Fable otrzymał bramkę `FAKT_BEZ_POKRYCIA`. Usunął wyłącznie to zdanie.
Tytuł, podtytuł i całe pozostałe body są bajtowo identyczne z artykułem w
sekcji 3.

Dokładny opis zmian zwrócony przez model:

> Deleted the final sentence claiming the records prove the system prevented
> exactly 12 accidents; the evidence card contains no accident data, the audit
> did not measure safety, and the card explicitly states no safety effect is
> established. The existing limits paragraph already covers this gap, so no
> replacement text was needed.

Koszt rewizji: 0,156150 USD. Live re-review i form-review nie wykonały się,
ponieważ ramię DeepSeek zatrzymało się na Scoucie.

## 6. Pięć Notes Opus

Wszystkie Notes używały tego samego zamrożonego faktu:

> Mains-powered clocks keep time by counting electricity-grid cycles. In early
> 2018, a prolonged frequency deviation below 50 Hz in Continental Europe
> caused synchronous clocks to fall about six minutes behind.

Źródło wejściowe:
[ENTSO-E, 6 marca 2018](https://www.entsoe.eu/news/2018/03/06/press-release-continuing-frequency-deviation-in-the-continental-european-power-system/).
Źródło nie zostało ponownie pobrane ani sprawdzone w tym przebiegu. DeepSeek
fact-check nie wystartował, dlatego każda Note ma `safe_to_post=false`.

### PROSTA — 47 słów

Six minutes went missing from mains-powered clocks across Europe in early 2018. Those clocks don't measure time at all. They count grid cycles, nominally 50 per second, so when Continental Europe's frequency sagged below 50 Hz for a prolonged stretch, every one of them quietly fell behind.

### LICZBA — 49 słów

Six minutes.

That's how far behind mains-powered clocks across Continental Europe ran in early 2018. Clocks plugged into the wall don't measure time. They count grid cycles, nominally 50 Hz, and when the frequency sat below that for long enough, every one of them quietly lost the same minutes.

### SCENA — 50 słów

Your oven clock doesn't measure time. It counts mains cycles.

Fifty per second, nominally. In early 2018 a long frequency deviation across Continental Europe pushed the grid below 50 Hz, and synchronous clocks drifted about six minutes behind. Nothing was broken in the kitchen. The electricity itself was running slow.

### ODWROCENIE — 48 słów

Your oven clock isn't measuring time. It counts cycles of mains electricity, 50 per second, and calls that a second.

In early 2018 the Continental European grid drifted below 50 Hz and stayed there.

Clocks across the continent fell about six minutes behind. None of them were broken.

### ZACZEP_I_KONKRET — 52 słowa

Your oven clock doesn't measure time. It counts cycles of the mains supply, nominally 50 Hz, and nothing else.

In early 2018 a prolonged frequency dip below 50 Hz hit the Continental European grid. ENTSO-E reported synchronous clocks across the continent running about six minutes behind.

Check your oven against your phone.

## 7. Czego nadal nie ma do pokazania

Brak nie jest ukrywany ani zastępowany fixture'em:

- brak pomysłów zwróconych przez live Scouta;
- brak live feasibility i wyboru tematu;
- brak wyszukiwania oraz listy publicznych źródeł dla artykułu;
- brak live klasyfikacji źródeł i syntezy;
- brak DeepSeek review oraz form-review obu artykułów;
- brak dwóch ślepych sędziów stylu A/B;
- brak re-review po rewizji;
- brak fact-checku pięciu Notes.

Normalny V3 nie może nazwać tych etapów wykonanymi. Po trzech nierozliczonych
awariach DeepSeek są one `NOT_RUN`, a nie PASS ani FAIL jakości modelu.

# C5 provider contract freeze — kiedy „domyślne” przestaje być neutralne

Data: 2026-08-10  
Etap roadmapy: 3  
Status: `C5 PROVIDER CONTRACT FREEZE — CANDIDATE COMPLETE — AWAITING INDEPENDENT REVIEW`

## Punkt wyjścia

Poprzednia fala została zamknięta i zweryfikowana po merge na `main=75815de495936b637bb7a6ed86b79006dd9b7447`. Kod znał już modele, ceny, frozen bindingi i kontrolowany lifecycle kwalifikacji, lecz dwa istotne parametry transportu Anthropic nadal pozostawały domyślne: geografia inferencji oraz service tier.

To drobna różnica w kodzie, ale duża różnica w odpowiedzialności. Workspace może mieć własne `default_inference_geo`, a `service_tier=auto` może wybrać Priority. Budżet i capability zostały tymczasem policzone dla GLOBAL + STANDARD. Bez jawnych parametrów rachunek opierał się na kontekście konta, którego repo nie kontrolowało.

## Co zmieniła fala

Każdy controlled Anthropic request wysyła teraz bezwarunkowo:

- `inference_geo="global"`;
- `service_tier="standard_only"`.

Stałe nie mają env/config override. Test symuluje jednocześnie workspace US, dostępny Priority Tier i nieprzychylne zmienne środowiskowe; request nadal ma frozen wartości.

Jeżeli odpowiedź udostępnia `usage.inference_geo` i `usage.service_tier`, system dodatkowo wymaga `global` i providerowego enumu `standard`. Zwrócone `us` albo `priority` nie może stać się sukcesem. Ponieważ external effect już nastąpił, system zachowuje usage i wyliczony koszt, terminalizuje fail-closed oraz nie ponawia requestu.

## Odmowa z kodem HTTP 200

Fable może zwrócić technicznie poprawną odpowiedź z `stop_reason="refusal"`. Wcześniej warstwa aplikacyjna nie nazywała tej sytuacji dostatecznie jasno. Teraz identity i usage nadal są sprawdzane, koszt pochodzi z frozen fingerprinted pricing i `Decimal`, ale rezultat nie jest PASS, capability nie staje się VERIFIED, a fallback, retry i drugi caller pozostają zerowe.

To ważny wzorzec: sukces transportu nie jest sukcesem zadania.

## Retencja nie jest checkboxem globalnym

Fable 5 wymaga akceptacji 30-dniowej retencji danych. Fala nie zmieniła prawdziwego workspace i nie udawała decyzji człowieka. Zamiast globalnej flagi powstał append-only, wygasający dowód związany z dokładnym:

- providerem i modelem;
- lifecycle scope;
- approvalem;
- requestem albo jobem;
- policy reference, osobą akceptującą i oknem czasu.

Brak, zła tożsamość lub wygaśnięcie blokuje przed callerem, konsumpcją approvalu i kosztem. Testy korzystają wyłącznie ze sztucznego evidence w nowych tymczasowych bazach.

**FABLE REAL QUALIFICATION BLOCKED UNTIL OWNER ACCEPTS 30-DAY RETENTION**

To oczekująca decyzja właściciela, nie defekt implementacji. Sam wcześniejszy wybór Fable nie jest zgodą na warunki retencji.

## Uczciwa granica czasu Sonneta

Źródło providerowe podaje ceny promocyjne „through August 31” i standardowe „starting September 1”, lecz nie dokładną sekundę ani strefę. Repo nadal potrzebuje deterministycznej granicy, dlatego UTC timestamp pozostał lokalną, konserwatywną normalizacją policy. Dokumentacja nie przypisuje go Anthropicowi.

## Dowód i koszt

- nowe testy: `22/22`;
- affected: `330/330`;
- full suite: `2481/2481` w `509,91 s`;
- collect/exact unique: `2481/2481`, duplikaty `0`;
- `compileall` i `git diff --check`: PASS;
- rzeczywisty koszt: `0.000000 USD`.

Konserwatywny koszt C5 dla GLOBAL + STANDARD pozostał bez zmian: qualification `0.442880`, execution `0.496000`, razem `0.938880 USD`. Wartość `1.032768 USD` dla US 1.1× jest wyłącznie kontrfaktycznym dowodem potrzeby gate, nie dozwoloną ścieżką budżetową.

Produkcja pozostała na schemacie `0020_topic_generation_lifecycle`; migracja produkcyjna, rehearsal, real qualification, real API, C5 i publikacja nie rozpoczęły się. F5 i F6 świadomie pozostały poza zakresem. Nie wykonano stage, commita, pushu, PR ani merge.

Najkrótsza lekcja tej fali brzmi: domyślna wartość nie usuwa decyzji — tylko przenosi ją poza audytowalny kontrakt systemu.

## Dopisek 2026-08-10 — przygotowanie authority package bez wykonania

Po produkcyjnej migracji do `0030` odtworzyliśmy cały przyszły łańcuch Fable wyłącznie offline. Repo potrafi deterministycznie wskazać model, cenę, fingerprinty i token envelope, a temp rehearsal dowiódł caller-once, frozen pricing, one-shot approvalu i braku częściowego stanu przy odmowach przed efektem.

Trace ujawnił dwie decyzje, których kod nie ma prawa podjąć za właściciela. Po pierwsze, repo nie zawiera prawdziwego external reference do polityki 30-dniowej retencji; samo pole jest opaque stringiem, więc fingerprint chroni niezmienność wskazania, nie jego prawdziwość. Po drugie, produkcyjny `ARTICLE_WRITER` nadal ma bootstrapową policy `UNVERIFIED`, mimo że rodzina `FABLE` jest już ustalona.

Nie zapisano katalogu, ceny, evidence, approvalu ani acceptance do produkcji. Nie uruchomiono API, qualification, C5 ani publikacji. Pakiet kończy się statusem `READY FOR OWNER INPUT`, a nie zgodą na następny krok.

# Charakter Nothing Is Accidental

Research i zmiany: 25 września 2026. Zakres: notki, komentarze, odpowiedzi,
restacki oraz wspólny głos używany podczas naprawy krótkiego tekstu.

## Co znaleziono

| Źródło pierwotne | Przydatny wzorzec | Zastosowanie tutaj |
| --- | --- | --- |
| [ElizaOS: Personality and Behavior](https://docs.elizaos.ai/agents/personality-and-behavior) i [Character Interface](https://docs.elizaos.ai/agents/character-interface) | Spójna osobowość, przykłady wypowiedzi i dostosowanie tonu do sytuacji. | Wspólna karta redaktora śledczego, trzy autorskie przykłady osądu, rozróżnienie notki, komentarza, odpowiedzi i restacka. |
| [personagent](https://github.com/wangkant/personagent) | Konkretne nawyki zamiast samego „brzmij naturalnie”; pamięć rozdzielona między rozmowy; uczenie na sprawdzonych korektach. | Konkretne zasady przyjmowania sprostowań; pamięć opublikowanych wypowiedzi pozostaje rozdzielona między kanały. Nie wdrażamy automatycznego przejmowania instrukcji czytelników. |
| [Social Agent](https://github.com/bravian1/social-agent) | Osobny profil, historia wypowiedzi oraz rejestry obserwowanego zaangażowania i liczby obserwujących. | Historia pomaga wykryć powtarzany rytm pytań. Same polubienia nie zmieniają automatycznie osobowości ani przekonań. |
| [Anthropic: Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) | Proste rozwiązania i ewaluacja przed dodawaniem kolejnych etapów. | Lokalna wskazówka stylistyczna bez dodatkowego wywołania LLM; płatne porównanie przed/po na tych samych przypadkach. |

To inspiracje implementacyjne, nie dowody szybszego wzrostu subskrypcji.
Nie znaleziono w tych materiałach porównywalnego badania wzrostu Substacka.
Nie kopiujemy cudzej persony, biografii ani treści.

## Docelowy charakter

Dociekliwy redaktor, który rozumie użyteczne wynalazki, sprawdza zbyt szerokie
obietnice i umie połączyć decyzję z bodźcami ekonomicznymi. Wyrazistość bierze
się z wyboru szczegółu i własnego osądu. Nie wymaga stałego sprzeciwu.
Interes ekonomiczny jest przesłanką do badania hipotezy, nie dowodem ukrytego
zamiaru. Pytanie pojawia się wtedy, gdy odpowiedź zmieni ocenę sprawy.

Odpowiedź na sprostowanie zaczyna się od sprawdzenia, kto ma rację. Przy
oczywistym błędzie liczbowym przyznaje błąd bez wymówki. Nie twierdzi, że
opublikowany tekst został zmieniony, jeżeli nie ma potwierdzenia edycji.
Na bezpośrednie pytanie o użycie AI odpowiada zgodnie z prawdą.

## Wdrożenie

- `prompts/glos_krotkich.md`: wspólna osobowość, różne rejestry i krótkie
  przykłady zachowania, wyraźnie oddzielone od dowodów do publikacji.
- `prompts/komentarz.md`: nieznana właściwość nie jest automatycznie wadą
  i nie musi kończyć się kolejnym pytaniem kontrolnym. Wyjaśnienie korzyści
  jest pełnoprawnym wkładem. Wymieniona przesłanka eskalacji nie oznacza,
  że innych kontroli nie ma.
- `prompts/restack.md`: przewaga ekonomiczna pozostaje hipotezą, jeśli brak
  pomiaru. Istniejący zespół nie dowodzi najniższego kosztu nowego obowiązku.
- `prompts/odpowiedz.md`: usunięta obowiązkowa obrona stanowiska oraz odmowa
  odpowiedzi o AI; skrócone powtórzenia porad stylistycznych.
- `stages.pamiec_glosu`: po dwóch ostatnich różnych, udanych publikacjach
  danego rodzaju zawierających pytajnik sugeruje inną formę wypowiedzi.
  Liczy pytajnik przed skróceniem próbki. To prosta heurystyka, nie analiza
  intencji ani zakaz zadawania pytań. Błędne rekordy, szkice i duplikaty nie
  tworzą fałszywej serii. Materiał historyczny pozostaje niezaufany.
- `stages.reply_to`: otwarcie wynika z konkretnego pytania czytelnika;
  usunięto losowanie sugestii otwarcia.

Zmiana nie dodaje zależności ani wywołań API do zwykłego przebiegu. Dłuższa
karta głosu zwiększa część wejścia, krótszy prompt odpowiedzi zmniejsza inną.
To nie jest obietnica zerowego kosztu tokenów. Routing modeli jest zachowany:
DeepSeek dla krótkich form, Fable dla artykułów.

## Weryfikacja

`tests/test_voice_delivery.py` sprawdza pamięć na udanych publikacjach,
oddzielenie kanałów, duplikaty, pytanie poza obciętym fragmentem i otwarcie
odpowiedzi bez losowania. Istniejące testy kontrolują wspólny głos i Fable.

Płatny `tests/platne/proba_charakteru.py` przechwytuje prompt z prawdziwych
funkcji etapów tuż przed pisaniem, następnie wykonuje rzeczywiste wywołanie
modelu. Porównuje dziesięć przypadków przed i po zmianie. Przypadki są jawnie
testowe; nie udają wiadomości czytelników. To test pisania, nie test publikacji
ani całego researchu. Żaden szkic nie trafia do Substacka. Wyniki JSON i koszty
są zapisywane po każdym wywołaniu; istniejący plik chroni przed przypadkowym
ponownym opłaceniem testu. Osobna ręczna ocena jest niezbędna, bo poprawny JSON
nie dowodzi dobrego stylu.

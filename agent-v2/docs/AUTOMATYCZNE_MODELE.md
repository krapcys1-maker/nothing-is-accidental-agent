# Automatyczne wersje modeli Nothing Is Accidental

Kontrola odbywa się przy uruchomieniu dnia oraz przed artykułem, maksymalnie raz
na 24 godziny. Nie wymaga osobnego harmonogramu. Oficjalne listy API Anthropic,
DeepSeek i OpenAI są pobierane bez wywołania modelu językowego.

Obsługiwane role: DeepSeek Flash, DeepSeek Pro jako zastępca wyszukiwania,
Fable, Opus, Sonnet oraz GPT Image. Artykuły pozostają w rodzinie Fable,
codzienna praca w rodzinie Flash. Opus i Sonnet pozostają obsługiwane także
w trybach dodatkowych, choć zwykły routing obecnie ich nie używa.

Nowa wersja tekstowa musi odpowiedzieć poprawnym JSON-em. Nowy DeepSeek musi
ponadto faktycznie użyć wyszukiwarki przez ten sam endpoint, którego używa
produkcja. Liczony jest wynik narzędzia w `usage`, nie deklaracja w tekście.
Nowy GPT Image musi wygenerować PNG o produkcyjnym rozmiarze i jakości.
Próbny obraz zostaje w `data/model-probes`; nie jest publikowany.

Flash używa obecnie nazwy `deepseek-flash`. Jeśli dostawca aktualizuje model
pod tą samą nazwą, korzystamy z aktualizacji bez zmiany identyfikatora.
Jeżeli alias znika i pojawia się następca z numerem, wybieramy go z listy API
i sprawdzamy przed użyciem. Numerowana wersja Fable, np. 5.2, jest porównywana
numerycznie z 5.1. Daty w nazwach snapshotów nie są numerami wersji.

W ramach GPT Image wybierana jest najwyższa stabilna wersja; przy tej samej
wersji pełny wariant Sunburst ma pierwszeństwo przed szybkim wariantem Flare.
Nazwy stabilne mają pierwszeństwo przed snapshotem tej samej wersji.
Warianty mini, preview, beta i eksperymentalne są pomijane.

Zmiana trafia najpierw atomowo do `data/wybor_modeli.json`, potem do routingu
bieżącego procesu. Kolejny proces czyta ten sam wybór. Brak dostępu, błędny
JSON, brak wyszukiwania, nieprawidłowy obraz lub błąd zapisu pozostawiają
dotychczasowy model danej roli. Zniknięcie bieżącej wersji z listy nie wystarcza
do cofnięcia: starszy zamiennik może wejść dopiero po nieudanej próbie obecnego.
Jawne `AGENT_V2_WRITER` zachowuje przypięcie pisarza w danym uruchomieniu.

Próby podlegają zwykłym limitom kosztów i wyłącznikom. Grafika jest księgowana
z tokenów zwróconych w `usage`, gdy są dostępne. Cenniki nie są automatycznie
pobierane z internetu: nieznany przyszły model dostaje oznaczony szacunek swojej
rodziny. To nie jest potwierdzenie ceny na fakturze. Znaczna podwyżka ceny lub
zmiana schematu API może wymagać aktualizacji kodu; test dostępności nie jest
testem jakości wszystkich przyszłych tekstów.

`aktualne_modele.py` to oddzielny katalog wiedzy do promptów. Jego błąd JSON
nie zatrzymuje mechanizmu przełączania, który korzysta z list API dostawców.

Dokumentacja sprawdzona 25 września 2026:

- [Anthropic: lista modeli i paginacja](https://platform.claude.com/docs/en/api/models/list)
- [DeepSeek: lista modeli](https://api-docs.deepseek.com/api/list-models/)
- [OpenAI: lista modeli](https://developers.openai.com/api/reference/resources/models/methods/list)
- [OpenAI: generowanie obrazów](https://developers.openai.com/api/docs/guides/image-generation)
- [OpenAI: stawki obrazów](https://developers.openai.com/api/docs/pricing)

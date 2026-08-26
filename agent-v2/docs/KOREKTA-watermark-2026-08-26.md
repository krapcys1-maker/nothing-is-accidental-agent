# Korekta: „The Watermark Was Never a Verdict"

Artykuł: https://nothingisaccidental.substack.com/p/the-watermark-was-never-a-verdict
Opublikowany 25 sierpnia 2026. Korekta ustalona 26 sierpnia 2026.

## Co jest nie tak

Dwie rzeczy, obie w tej samej sprawie — kalifornijskiej SB 942.

**1. Zdanie lobbystów wydrukowane jako ustalenie komisji.** Zdanie „there isn't
a program that can watermark text" naprawdę stoi w analizie Senate Judiciary
Committee — jako blok cytatu od koalicji lobbującej PRZECIW ustawie (CalChamber,
CCIA, NetChoice, TechNet). Linijka nad nim brzmi: „A coalition in opposition,
including Technet, writes:". Własne słowa komisji, kilka wierszy wyżej, są
znacznie słabsze i o tekście nie mówią nic szczególnego. Poparcia dla ustawy
odnotowano: żadnego.

**2. Nieaktualny stan prawa opisany w czasie teraźniejszym.** Ustawodawca
wykreślił tekst z obowiązków między lipcem a sierpniem 2024 — dokładnie tak, jak
prosiła opozycja. Ustawa obowiązująca od 2 sierpnia 2026, czyli trzy tygodnie
przed naszą publikacją, obejmuje obraz, wideo i dźwięk. Słowo „text" występuje w
całym rozdziale raz, w definicji SYSTEMU, nie tego, co trzeba oznaczyć. Obowiązek
znakowania NIEWIDOCZNEGO nie obejmował tekstu w żadnej wersji ustawy.

Kara 5 000 USD i próg miliona użytkowników są poprawne — sprawdzone u źródła.

**Teza artykułu przeżywa w całości** i prawdziwa historia jest jej LEPSZYM
dowodem: postawiony przed zarzutem, że technologia weryfikacji dla jednego medium
nie istnieje, ustawodawca nie sfinansował wykrywania i nie porzucił obowiązku —
usunął medium z zakresu i zostawił architekturę ujawnienia nietkniętą. To jest
reżim ujawnienia zachowujący się dokładnie tak, jak teza przewiduje.

---

## Poprawki do wklejenia

### 1. PODTYTUŁ

Zastąpić:

> AI-text labelling laws rest on a technology their own drafters call unworkable — because detection was never the point.

na:

> AI-text labelling laws rest on a technology the industry told legislators does not exist — because detection was never the point.

### 2. AKAPIT PIERWSZY

Zastąpić dwa zdania od „The committee was analysing SB 942…" do „…impossible to
comply with." na:

> The committee was analysing the March 2024 draft of SB 942, which then required large generative-AI providers to put a visible, hard-to-remove label and provenance metadata on AI-generated text, images, video and multimedia. Printed in the same analysis is a block quote from the bill's industry opponents: there isn't a program that can watermark text, making the requirement impossible to comply with — so, they asked, strike text from the bill.

### 3. AKAPIT DRUGI, zdanie otwierające

Zastąpić:

> A legislature demanding something its own analysts call impossible looks like farce.

na:

> The Senate passed that version with the objection printed in the floor analysis in front of it; the Assembly then quietly struck text from the duties, and the law that took effect this month covers only image, video and audio. My reading is that the retreat is the tell: the watermark's legal job was never detection.

### 4. AKAPIT O KALIFORNII

Po „…civil penalty of $5,000 per violation," dodać:

> — in the enacted version, operative since 2 August 2026, for image, video and audio only.

W tym samym akapicie zmienić przykład ilustrujący, żeby mieścił się w realnym
zakresie ustawy:

> a machine-written article circulating unlabelled

na:

> a machine-made image circulating unlabelled

### 5. AKAPIT O OGRANICZENIACH

Zastąpić:

> SB 942 arrives through a committee analysis of a bill, not the adopted statute, so what California ultimately enacted may differ from what the analysts read.

na:

> The version analysed in April 2024 is not the law; text was removed before enactment.

### 6. ŹRÓDŁA — dopisać

> California AI Transparency Act, Bus. & Prof. Code §§22757–22757.6 (SB 942, Stats. 2024, Ch. 291, as amended by AB 853, Stats. 2025, Ch. 674) — leginfo.legislature.ca.gov

### 7. STOPKA — nota o korekcie

> Corrected 26 August 2026: an earlier version attributed to the Senate Judiciary Committee a statement that was a quotation from the bill's industry opponents, and described SB 942 as requiring imperceptible marking of AI-generated text. The March 2024 draft required a visible label and metadata on text; the imperceptible-marking duty never covered text, and the enacted law, operative 2 August 2026, covers image, video and audio only.

---

## Co poprawione w systemie, żeby się nie powtórzyło

- `86c22a9` — `zweryfikuj()` przed publikacją artykułu. Wcześniej artykuł szedł
  w świat bez sprawdzenia faktów, a notka o nim je miała.
- `86c22a9` — `dyskoveria.md` 6b: twierdzenie o tym, co wymaga prawo, sprawdza
  się w tekście uchwalonym. 6c: cytat wewnątrz dokumentu urzędowego nie jest
  głosem tego dokumentu.
- `86c22a9` — te same dwie reguły w `weryfikacja.md`, bo to ona jest ostatnią
  bramą.
- następny commit — jedno „nie" od sprawdzania faktów zdejmuje artykuł z kolejki
  promocyjnej NA STAŁE. Notka promująca odpadła o 21:44 przy 13 wyszukiwaniach,
  a o 00:43 inna notka o tym samym dostała 22 wyszukiwania i przeszła. Bramkę
  losową, do której wraca się nazajutrz, po prostu się w końcu przechodzi.

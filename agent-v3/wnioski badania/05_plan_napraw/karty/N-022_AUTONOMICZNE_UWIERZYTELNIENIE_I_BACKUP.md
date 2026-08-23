# N-022 — autonomiczne uwierzytelnienie i backup

- **Status:** `OPEN; PLATFORM_CONTRACT_REQUIRED`
- **Ustalenie:** A-100
- **Zakres:** odnowienie sesji testowej/produkcyjnej i wspierany eksport danych

## Hipoteza

Pełna autonomia operacyjna jest możliwa tylko wtedy, gdy platforma oferuje
wspierany, automatyzowalny kontrakt odnowienia uwierzytelnienia i eksportu.
Bez niego utrata sesji lub brak kopii musi blokować promocję, a nie uruchamiać
nieudokumentowane obejścia.

## Reuse

Zachować walidator pliku sesji, alarm wygasania, walidację CSV, porównanie
liczebności i retencję. Zastąpić ręczne dostarczenie wspieranym źródłem danych,
jeżeli takie źródło zostanie potwierdzone.

## Badania wymagane

1. Zweryfikować aktualne oficjalne możliwości auth/export bez sondowania
   prywatnych endpointów.
2. Zdefiniować rotację sekretu i odzyskanie po wygaśnięciu.
3. Testować wyłącznie na odseparowanym koncie.
4. Dowieść szyfrowania, retencji i braku danych osobowych w release bundle.
5. Jeżeli platforma nie oferuje kontraktu, oznaczyć `AUTONOMOUS_PRODUCTION_BLOCKED`.

## Kryterium końca

Restart i wygaśnięcie sesji nie wymagają interaktywnej procedury, a aktualna
kopia jest tworzona i weryfikowana zgodnie ze wspieranym interfejsem platformy.


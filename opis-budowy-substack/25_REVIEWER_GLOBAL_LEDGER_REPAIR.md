# Reviewer miał koszt, ale globalny budżet go nie widział

Najciekawszy błąd nie polegał na braku liczenia. Koszt Reviewera był policzony i odejmowany od limitu artykułu. Tyle że dzienny i miesięczny budżet patrzyły na inny rejestr — `model_usage` — a tam Reviewera nie było.

Naprawa połączyła te dwa światy. Zakończenie płatnego review i wpis do kanonicznego ledgeru są jedną transakcją. Rekord musi zgadzać się z zamrożonym providerem, modelem, tokenami i ceną, a potem nie może zostać zmieniony ani usunięty. Nieznany wynik nadal nie jest zerem: utrzymuje rezerwację.

Druga lekcja była procesowa. Nie każdy brak nazwany w review jest blockerem bieżącego etapu. Modelowy novelty był świadomie odrzuconym wariantem, a przebudowa realnego A1/A2/B łamałaby zakaz zmiany research pipeline’u w Etapie 3.

Status: kandydat do niezależnego review. Produkcja pozostała na schema `0032`; migracja `0033`, realne API i smoke wymagają osobnych zgód. Koszt rzeczywisty: `0.000000 USD`.

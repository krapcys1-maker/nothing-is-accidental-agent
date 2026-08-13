# REVIEW-ONLY nie jest retry

Po dwóch utraconych odpowiedziach najłatwiejszym błędem byłoby nazwać kolejne wywołanie „ponowieniem”. To ukryłoby najważniejszy fakt: poprzednie efekty mogły wydarzyć się po stronie providera, choć lokalnie nie mamy ich usage ani request ID.

Dlatego nowa droga nie reużywa execution ref i nie otwiera starego joba. Dostaje własny approval związany z jednym hashem istniejącego draftu, jednym modelem, limitem kosztu i czasem ważności. Czeka na kompletną finalną wiadomość streamu. Zerwanie nie staje się pustą odpowiedzią ani kosztem zero.

Najbardziej praktyczna bariera pojawia się jeszcze wcześniej: dopóki stare v1/v4/v5 mają nierozstrzygniętą ekspozycję, REVIEW-ONLY nie dochodzi do SDK. System wymaga zewnętrznej rekonsyliacji zamiast technicznego obejścia.

Produkcja pozostaje na schema `0038` z 38 migracjami. Proponowana `0039` i pierwszy REVIEW-ONLY wymagają osobnych decyzji. W tej pracy nie było requestu online, publikacji ani nowego kosztu.

Domknięty kandydat rozróżnia też „kolejny etap” od retry. Jeśli pierwszy reviewer żąda korekty, jego dokładny, trwały wynik staje się instrukcją dla istniejącego mechanizmu writer attempt 2. Potem działa nowy reviewer z własną identity. Druga prośba o rewrite nie otwiera trzeciej rundy — zatrzymuje materiał dla człowieka. Po crashu następny krok wynika wyłącznie z tego, co zostało już trwale zapisane, więc udany etap nie jest wykonywany ponownie.

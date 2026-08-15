# Udane pobranie to nie użyteczne źródło

Dwa tematy w bazie mają wszystko, za co zapłaciliśmy: wyszukiwanie źródeł, zgody, udane pobrania. Nie mają artykułu. Nie mają nawet karty researchu. Nic nie zgłosiło błędu — po prostu w pewnym momencie przestało się dziać.

Przyczyna jest arytmetyczna i przez to niewidoczna. Model dostaje korpus w jednym kawałku i ma twardy limit wejścia: 23 808 tokenów. Nasz packer nie dzieli dokumentów — albo strona wchodzi w całości, albo nie wchodzi wcale. Przy przeliczniku 3,5 znaku na token oznacza to, że strona dłuższa niż mniej więcej 83 tysiące znaków jest bezużyteczna zawsze, niezależnie od tego, co zawiera i ile kosztowało jej pobranie.

Temat 58 pobrał trzy źródła. Trzecie ma 48 743 znaki, czyli 24 388 tokenów. Samo, bez żadnego towarzystwa, nie mieści się w limicie. Zostają dwa źródła. Próg wynosi trzy. Packer zgłasza, że korpus jest niekompletny, funkcja nadrzędna zwraca „jeszcze nie" — i to jest koniec historii. Temat 68 przewrócił się tak samo, na stronie o 61 747 znakach.

Warto zauważyć podwójny koszt. Taka strona nie tylko nie wnosi nic do korpusu; wcześniej zajęła jeden z sześciu slotów kandydata i jedno pobranie. Przy założeniu, że mniej więcej połowa poważnych źródeł i tak odmawia automatowi, sześciu kandydatów zostawiało trzy udane pobrania — dokładnie próg, zero zapasu — a teraz widać, że nawet to „dokładnie próg" bywa złudzeniem, bo jedno z tych trzech może się nie zmieścić.

Błąd projektowy nie polega na limicie ani na progu. Polega na tym, że liczyliśmy nie to, co trzeba. „Trzy udane pobrania" brzmi jak spełniony warunek, ale warunkiem jest „trzy źródła, które zmieszczą się w kopercie". Te dwie liczby rozjeżdżają się cicho i dopiero po fakcie.

Doraźna odpowiedź jest prosta i tania: prosić o więcej, niż potrzeba. A1 pyta teraz o dziesięciu kandydatów zamiast sześciu i zakłada, że część odpadnie — jedni przez 403, inni przez rozmiar. To nie usuwa problemu dużych stron, tylko daje mu zapas.

Przy okazji zniknął sztywny cennik rezerwacji. Wcześniej wolno było zarezerwować dokładnie jedną z czterech kwot, a wyszukiwanie kosztujące 1,17 USD przy rezerwacji 0,60 USD ginęło w połowie wywołania i marnowało całą próbę razem z pieniędzmi. Rezerwacja nie jest prognozą. Ma nieść margines, więc jest teraz zwykłym zakresem z sufitem, a nie listą dozwolonych liczb.

Jedno zastrzeżenie, żeby nie udawać precyzji, której nie mam: domyślna rezerwacja została wyliczona z pomiaru przy sześciu kandydatach, przeskalowanego na dziesięciu. To ekstrapolacja, nie pomiar. Pierwszy realny przebieg ma ją zastąpić prawdziwą liczbą.

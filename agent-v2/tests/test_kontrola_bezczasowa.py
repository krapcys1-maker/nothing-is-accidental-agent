# -*- coding: utf-8 -*-
"""Prog wieku dokumentu kontrolnego dotyczy tylko twierdzen o STANIE DZIS.

DLACZEGO TO POWSTALO. Przebieg produkcyjny 30 sierpnia oplacil osiem faktow i
wyrzucil piec z nich na jednym progu: „dokument kontrolny ma N dni (prog 90)".
Cztery z tych pieciu byly bezczasowe — liczba genow kodujacych bialko, prefill
czytajacy caly prompt naraz, kuracja danych treningowych, badanie podluzne.
Dla takiego faktu nie istnieje swiezszy dokument rzadzacy, bo nic sie nie
zmienilo, wiec prog nie chronil przed niczym i kosztowal 62% partii.

Gorsza polowa tej samej wady: model, ktory daty NIE PODAWAL, przechodzil. Kara
spadala na precyzje. Ten plik pilnuje obu polowek naraz.

KAZDY TEST MA KONTRDOWOD. Cztery z ponizszych oblewaja na kodzie sprzed
poprawki — dwa dlatego, ze bezczasowy fakt byl odrzucany, i dwa dlatego, ze
pominiecie daty przy twierdzeniu o dzis bylo latwiejsza droga niz jej podanie.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
import stages  # noqa: E402


def _dni_temu(ile: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=ile)).strftime("%Y-%m-%d")


STARY = _dni_temu(config.MAKS_WIEK_ZRODLA_DNI + 80)
SWIEZY = _dni_temu(10)

# Fakt bezczasowy: nie nazywa wersji i nie mowi o stanie dzis. Zdanie o
# badaniu podluznym — dokladnie ta klasa, ktora produkcja wyrzucila.
BEZCZASOWY = (
    "In a 12-month longitudinal study, participants who used a conversational "
    "assistant every day described their own reasoning differently afterwards."
)

# Twierdzenie o stanie dzis: dwa slowa z `TWIERDZI_O_TERAZ`.
O_DZIS = (
    "The newest model from that lab supports a context window an order of "
    "magnitude larger than the one before it."
)


def _fakt(tresc: str, **pola) -> dict:
    baza = {
        "fact": tresc,
        "actually": "",
        "wrong_belief": "",
        "consequence": "",
        "decision": "",
        "source_date": SWIEZY,
        "control_verdict": "CONFIRMS",
    }
    baza.update(pola)
    return baza


def test_atrapy_sa_tym_czym_mysle():
    """Zanim cokolwiek sprawdzimy — czy atrapy naprawde sa tym, za co je biore.

    Test na atrapie, ktora nie ma zakladanej wlasciwosci, dowodzi tylko tego,
    ze kod cos zwraca. Ta sesja spalila na tym dosc czasu.
    """
    assert not stages.nazywa_wersje(BEZCZASOWY), "bezczasowy nie moze nazywac wersji"
    o_teraz = [s for s in config.TWIERDZI_O_TERAZ if s in BEZCZASOWY.lower()]
    assert not o_teraz, "bezczasowy nie moze mowic o stanie dzis, a mowi: %r" % o_teraz
    assert [s for s in config.TWIERDZI_O_TERAZ if s in O_DZIS.lower()], \
        "atrapa 'o dzis' musi trafiac w slownik czasu terazniejszego"


def test_bezczasowy_ze_starym_dokumentem_przechodzi():
    """KONTRDOWOD: przed poprawka to bylo odrzucane, i to kosztowalo pieniadze."""
    ok, powod = stages.swiezosc_faktu(_fakt(
        BEZCZASOWY,
        control_date=STARY,
        control_url="https://example.org/study",
        control_fact="searched, nothing newer than the source changes the finding",
    ))
    assert ok, "bezczasowy fakt z prawdziwym starym dokumentem ma przechodzic: %s" % powod


def test_bezczasowy_ze_starym_dokumentem_ale_bez_sladu_odpada():
    """Dokument bez zdania o sprawdzeniu to nie jest kontrola, tylko odnosnik."""
    ok, powod = stages.swiezosc_faktu(_fakt(
        BEZCZASOWY,
        control_date=STARY,
        control_url="https://example.org/study",
        control_fact="",
    ))
    assert not ok
    assert "sladu szukania" in powod, powod


def test_twierdzenie_o_dzis_ze_starym_dokumentem_nadal_odpada():
    """Prog zostaje tam, gdzie mial sens. Uklad z Kenii wygladal dobrze."""
    ok, powod = stages.swiezosc_faktu(_fakt(
        O_DZIS,
        control_date=STARY,
        control_url="https://example.org/launch",
        control_fact="checked, unchanged",
    ))
    # Sprawdzamy ZASADE, nie brzmienie: ma odpasc i ma powiedziec, ze chodzi o
    # dokument kontrolny. Test przypiety do zdania pekalby przy kazdym
    # przeredagowaniu komunikatu, choc regula stalaby nietknieta.
    assert not ok
    assert "kontroln" in powod, powod


def test_twierdzenie_o_dzis_bez_daty_kontrolnej_odpada():
    """KONTRDOWOD: przed poprawka pominiecie daty PRZECHODZILO.

    To jest ta polowa wady, ktora nagradzala mniej informacji. Model z
    dokumentem w reku byl odrzucany, model bez dokumentu — nie.
    """
    ok, powod = stages.swiezosc_faktu(_fakt(
        O_DZIS,
        control_date="",
        control_fact="searched, nothing newer",
    ))
    assert not ok, "brak daty przy twierdzeniu o dzis nie moze byc latwiejsza droga"
    assert "bez daty kontrolnej" in powod, powod


def test_bezczasowy_bez_daty_ale_ze_sladem_przechodzi():
    """Ta sciezka istniala i ma zostac — dla faktu, ktory nie ma dokumentu."""
    ok, powod = stages.swiezosc_faktu(_fakt(
        BEZCZASOWY,
        control_date="",
        control_fact="searched, nothing newer than the source",
    ))
    assert ok, powod


def test_bez_daty_i_bez_sladu_odpada_zawsze():
    for tresc in (BEZCZASOWY, O_DZIS):
        ok, powod = stages.swiezosc_faktu(_fakt(
            tresc, control_date="", control_fact=""))
        assert not ok, tresc[:40]
        assert "bez sladu szukania" in powod, powod


def test_swiezy_dokument_przechodzi_w_obu_rodzajach():
    """Poprawka nie moze zepsuc sciezki, ktora dzialala."""
    for tresc in (BEZCZASOWY, O_DZIS):
        ok, powod = stages.swiezosc_faktu(_fakt(
            tresc,
            control_date=SWIEZY,
            control_url="https://example.org/doc",
            control_fact="checked today, unchanged",
        ))
        assert ok, "%s -> %s" % (tresc[:40], powod)


@pytest.mark.parametrize("werdykt", ["ENDS", "MODIFIES"])
def test_ends_i_modifies_nietkniete(werdykt):
    """Wlasciciel zatrzymal mnie raz na tej regule. Ma zostac, jak jest."""
    ok, _ = stages.swiezosc_faktu(_fakt(
        BEZCZASOWY, control_verdict=werdykt, control_date=STARY,
        control_fact="the arrangement was cancelled in the meantime"))
    assert ok
    ok, powod = stages.swiezosc_faktu(_fakt(
        BEZCZASOWY, control_verdict=werdykt, control_date=STARY,
        control_fact=""))
    assert not ok and "bez tresci" in powod, powod


if __name__ == "__main__":
    # Testy w tym repozytorium sa URUCHAMIANE JAKO SKRYPTY, po jednym pliku.
    # Bez tego bloku plik odpalony recznie nie zrobilby nic i wyszedl zerem —
    # czyli wygladalby na test, ktory przeszedl, nie wykonawszy niczego.
    import sys as _sys
    _sys.exit(pytest.main([__file__, "-q"]))

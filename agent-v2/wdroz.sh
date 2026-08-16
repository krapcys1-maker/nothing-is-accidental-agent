#!/usr/bin/env bash
# Wdrozenie nowej wersji z siecia bezpieczenstwa.
#
# Dotad wgrywalismy kod przez zwykly `git pull`. Jesli nowa wersja jest zepsuta,
# agent po prostu przestaje dzialac, a dowiadujemy sie o tym dopiero z kontroli
# ciszy — czyli po dobie milczenia na koncie.
#
# Tu jest odwrotnie: najpierw sprawdzamy, czy nowa wersja W OGOLE WSTAJE, i jesli
# nie, wracamy do poprzedniej, zanim ktokolwiek zauwazy.
set -euo pipefail

cd "$(dirname "$0")/.."
POPRZEDNIA=$(git rev-parse --short HEAD)
echo "  wersja przed wdrozeniem: $POPRZEDNIA"

# Nie wdrazamy w srodku przebiegu — zamek jest wtedy zajety.
if pgrep -f "run.py --dzien" >/dev/null; then
    echo "  PRZEBIEG TRWA — nie wdrazam, sprobuj po jego zakonczeniu"
    exit 1
fi

git fetch -q origin
NOWA=$(git rev-parse --short origin/main)
if [ "$POPRZEDNIA" = "$NOWA" ]; then
    echo "  nic nowego, wersja $NOWA juz jest"
    exit 0
fi
echo "  wciagam wersje: $NOWA"
git merge -q --ff-only origin/main

# --- SPRAWDZENIE, czy nowa wersja wstaje ------------------------------------
echo "  sprawdzam nowa wersje..."
if ! AGENT_V2_SERVER=1 .venv/bin/python -c "
import sys
sys.path.insert(0, 'agent-v2')
import config, db, llm, stages, browser, kanal, alarm, gates, style, run
assert config.MODEL_FOR and config.PRICING, 'pusta konfiguracja'
assert callable(browser.wystaw_notke) and callable(stages.notki_dnia)
assert config.OKNO_PUBLIKACJI_ET, 'brak okna publikacji'
print('  moduly wstaja i konfiguracja jest kompletna')
"; then
    echo "  NOWA WERSJA NIE WSTAJE — wracam do $POPRZEDNIA"
    git reset -q --hard "$POPRZEDNIA"
    exit 1
fi

# --- SPRAWDZENIE, czy sesja i konto nadal dzialaja --------------------------
if ! AGENT_V2_SERVER=1 timeout 180 .venv/bin/python -c "
import sys
sys.path.insert(0, 'agent-v2')
import browser
p, br, ctx = browser.podlacz_sie()
page = ctx.new_page()
try:
    assert browser.wlasciwe_konto(page), 'nie to konto albo brak sesji'
    print('  sesja i konto potwierdzone')
finally:
    page.close(); br.close(); p.stop()
"; then
    echo "  NOWA WERSJA NIE DOGADUJE SIE Z SUBSTACKIEM — wracam do $POPRZEDNIA"
    git reset -q --hard "$POPRZEDNIA"
    exit 1
fi

sudo cp agent-v2/systemd/*.service agent-v2/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
echo "  WDROZONE: $POPRZEDNIA -> $NOWA"
echo "  cofniecie jednym poleceniem:  git reset --hard $POPRZEDNIA"

#!/usr/bin/env bash
# Agent V3 jest prototypem badawczym. Ten artefakt celowo nie wdraża niczego.
set -euo pipefail

echo "ODMOWA: wdrozenie Agent V3 jest zablokowane przez kontrakt prototypu." >&2
echo "Dozwolone sa testy offline oraz jawnie odseparowane testy live_test." >&2
exit 64

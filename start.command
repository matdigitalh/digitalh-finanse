#!/bin/zsh
# Finanse lokalne: uruchomienie jednym kliknięciem. Serwer tylko na 127.0.0.1.
set -e
cd "${0:A:h}"
if [[ ! -x .venv/bin/python ]]; then
  echo "Pierwsze uruchomienie: przygotowuję środowisko…"
  python3 -m venv .venv
  .venv/bin/python -m pip install -q -r requirements.txt
fi
exec .venv/bin/python -m finanse.serwer "$@"

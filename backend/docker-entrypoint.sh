#!/usr/bin/env bash
set -euo pipefail

# Espera o Postgres, cria o schema se preciso, carrega os dados se o banco
# estiver vazio e só então sobe a API.
python -m roadie.cli db wait
python -m roadie.cli db init
python -m roadie.cli seed --if-empty
python -m roadie.cli create-admin --if-missing

exec "$@"

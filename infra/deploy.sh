#!/usr/bin/env bash
# Deploy no VPS. Roda no servidor, dentro de /opt/roadie, depois que o código
# já foi atualizado para origin/main (ver "Deploy automático" no README).
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE=(docker compose -f docker-compose.prod.yml -f docker-compose.vps.yml)

echo "==> $(git log --oneline -1)"
"${COMPOSE[@]}" up -d --build --remove-orphans db api web
docker image prune -f >/dev/null

# A API só responde depois de esperar o banco, aplicar o schema e a carga.
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8012/health >/dev/null && curl -fsS -o /dev/null http://127.0.0.1:3012/login; then
    echo "==> no ar: $(curl -fsS http://127.0.0.1:8012/health)"
    exit 0
  fi
  sleep 3
done

echo "==> a aplicação não respondeu em 90 s" >&2
"${COMPOSE[@]}" ps >&2
"${COMPOSE[@]}" logs --tail 40 api web >&2
exit 1

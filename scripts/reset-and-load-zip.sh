#!/usr/bin/env bash
# Borra todo (BD + cola) y carga un backup ZIP nuevo. Encola el job LLM al final.
# Uso: ./scripts/reset-and-load-zip.sh /ruta/al/chat.zip "Nombre del grupo"
# Requiere: docker compose up -d

set -e
cd "$(dirname "$0")/.."

ZIP="${1:?Falta path del ZIP. Uso: $0 /ruta/al/chat.zip \"Nombre del grupo\"}"
GROUP_NAME="${2:?Falta nombre del grupo. Uso: $0 /ruta/al/chat.zip \"Nombre del grupo\"}"

echo "=== 1. Truncando BD..."
PGPASSWORD=arbitool psql -h localhost -p 5433 -U arbitool -d arbitool_chat -f db/truncate_all.sql

echo ""
echo "=== 2. Vaciar cola LLM..."
redis-cli -p 6380 DEL arbitool:llm:jobs

echo ""
echo "=== 3. (Opcional) Borrar media anterior..."
if [[ -d "media" ]]; then
  rm -rf media
  mkdir -p media
  echo "    Media borrado."
fi

echo ""
echo "=== 4. Procesando ZIP (mensajes + encolar job LLM)..."
export PGPORT=5433
export REDIS_PORT=6380
npm run backup -- --file "$ZIP" --group-name "$GROUP_NAME"

echo ""
echo "=== Listo. Arrancá el worker: cd apps/llm-service && ./run-worker.sh"

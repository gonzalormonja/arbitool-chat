#!/usr/bin/env bash
# Trunca la BD y procesa el backup sin encolar LLM.
# Uso: ./scripts/truncate-and-import.sh
# Requiere: docker compose up -d (Postgres en 5433, Redis en 6380)

set -e
cd "$(dirname "$0")/.."

ZIP="/home/gonzalo/Descargas/WhatsApp Chat - juan ramon daniel.zip"
GROUP_NAME="juan ramon daniel"

echo "=== 1. Truncando tablas..."
PGPASSWORD=arbitool psql -h localhost -p 5433 -U arbitool -d arbitool_chat -f db/truncate_all.sql

echo ""
echo "=== 2. Procesando backup (solo mensajes, sin LLM)..."
export PGPORT=5433
export REDIS_PORT=6380
npm run backup -- --file "$ZIP" --group-name "$GROUP_NAME" --no-llm

echo ""
echo "=== Listo."

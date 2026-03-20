#!/usr/bin/env bash
# ============================================================
# PROCESAR NUEVO CLIENTE - Todo en uno
# ============================================================
# Uso:
#   ./scripts/nuevo-cliente.sh /ruta/al/chat.zip "Nombre del grupo"
#
# Opciones:
#   --no-llm    Solo importar mensajes, no procesar con LLM
#   --skip-reset No borrar datos anteriores (agregar al existente)
#
# Ejemplos:
#   ./scripts/nuevo-cliente.sh ~/Descargas/chat-juan.zip "Juan Perez"
#   ./scripts/nuevo-cliente.sh ~/Descargas/chat.zip "Maria" --no-llm
#   ./scripts/nuevo-cliente.sh ~/Descargas/chat.zip "Pedro" --skip-reset
#
# Requiere: docker compose up -d
# ============================================================

set -e
cd "$(dirname "$0")/.."

# ── Colores ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

step() { echo -e "\n${CYAN}=== $1${NC}"; }
ok()   { echo -e "${GREEN}    ✓ $1${NC}"; }
warn() { echo -e "${YELLOW}    ⚠ $1${NC}"; }
fail() { echo -e "${RED}    ✗ $1${NC}"; exit 1; }

# ── Parsear argumentos ──
ZIP=""
GROUP_NAME=""
NO_LLM=false
SKIP_RESET=false

for arg in "$@"; do
  case "$arg" in
    --no-llm)     NO_LLM=true ;;
    --skip-reset) SKIP_RESET=true ;;
    *)
      if [[ -z "$ZIP" ]]; then
        ZIP="$arg"
      elif [[ -z "$GROUP_NAME" ]]; then
        GROUP_NAME="$arg"
      fi
      ;;
  esac
done

if [[ -z "$ZIP" || -z "$GROUP_NAME" ]]; then
  echo "Uso: $0 /ruta/al/chat.zip \"Nombre del grupo\" [--no-llm] [--skip-reset]"
  exit 1
fi

if [[ ! -f "$ZIP" ]]; then
  fail "No se encontró el archivo: $ZIP"
fi

# ── Verificar que Docker está corriendo ──
step "0. Verificando servicios..."
if ! docker compose ps --status running 2>/dev/null | grep -q postgres; then
  warn "PostgreSQL no está corriendo. Iniciando docker compose..."
  docker compose up -d
  sleep 3
fi

if docker compose ps --status running 2>/dev/null | grep -q postgres; then
  ok "PostgreSQL OK (puerto 5433)"
else
  fail "No se pudo iniciar PostgreSQL"
fi

if docker compose ps --status running 2>/dev/null | grep -q redis; then
  ok "Redis OK (puerto 6380)"
else
  fail "No se pudo iniciar Redis"
fi

# ── Reset (si no se saltea) ──
if [[ "$SKIP_RESET" == false ]]; then
  step "1. Limpiando datos anteriores..."

  PGPASSWORD=arbitool psql -h localhost -p 5433 -U arbitool -d arbitool_chat -f db/truncate_all.sql -q
  ok "Base de datos truncada"

  redis-cli -p 6380 DEL arbitool:llm:jobs > /dev/null 2>&1
  ok "Cola Redis vaciada"

  if [[ -d "media" ]]; then
    rm -rf media
    mkdir -p media
    ok "Media anterior borrado"
  fi
else
  step "1. Saltando reset (--skip-reset)"
  warn "Los datos anteriores se mantienen"
fi

# ── Procesar ZIP ──
step "2. Procesando backup ZIP..."
echo -e "    Archivo: ${YELLOW}$ZIP${NC}"
echo -e "    Grupo:   ${YELLOW}$GROUP_NAME${NC}"

export PGPORT=5433
export REDIS_PORT=6380

BACKUP_ARGS="--file \"$ZIP\" --group-name \"$GROUP_NAME\""
if [[ "$NO_LLM" == true ]]; then
  BACKUP_ARGS="$BACKUP_ARGS --no-llm"
fi

eval npm run backup -- $BACKUP_ARGS

ok "Mensajes importados correctamente"

# ── Contar mensajes importados ──
MSG_COUNT=$(PGPASSWORD=arbitool psql -h localhost -p 5433 -U arbitool -d arbitool_chat -t -c "SELECT COUNT(*) FROM messages;" 2>/dev/null | tr -d ' ')
TRADE_COUNT=$(PGPASSWORD=arbitool psql -h localhost -p 5433 -U arbitool -d arbitool_chat -t -c "SELECT COUNT(*) FROM trades;" 2>/dev/null | tr -d ' ')
echo -e "    Mensajes en BD: ${GREEN}$MSG_COUNT${NC}"

# ── Procesar con LLM ──
if [[ "$NO_LLM" == true ]]; then
  step "3. Saltando LLM (--no-llm)"
  warn "Para procesar después: cd apps/llm-service && ./run-worker.sh"
else
  step "3. Iniciando worker LLM..."

  # Matar worker anterior si existe
  pkill -f "src.main" 2>/dev/null || true
  sleep 1

  cd apps/llm-service
  PYTHON="python3"
  [[ -x venv/bin/python ]] && PYTHON="venv/bin/python"

  # Iniciar worker en background
  $PYTHON -m src.main >> worker.log 2>&1 &
  WORKER_PID=$!
  cd ../..

  ok "Worker LLM arrancado (PID: $WORKER_PID)"
  echo -e "    Log: ${YELLOW}tail -f apps/llm-service/worker.log${NC}"
  echo ""

  # Monitorear progreso
  echo -e "${CYAN}    Esperando a que el LLM procese los mensajes...${NC}"
  echo -e "    (Ctrl+C para dejar corriendo en background)\n"

  PREV_TRADES=0
  STALL_COUNT=0
  while true; do
    sleep 10

    # Verificar que el worker siga vivo
    if ! kill -0 $WORKER_PID 2>/dev/null; then
      echo ""
      warn "Worker LLM terminó"
      break
    fi

    # Verificar si quedan jobs en la cola
    JOBS=$(redis-cli -p 6380 LLEN arbitool:llm:jobs 2>/dev/null || echo "?")

    # Contar trades y mensajes procesados
    TRADE_COUNT=$(PGPASSWORD=arbitool psql -h localhost -p 5433 -U arbitool -d arbitool_chat -t -c "SELECT COUNT(*) FROM trades;" 2>/dev/null | tr -d ' ')
    PROCESSED=$(PGPASSWORD=arbitool psql -h localhost -p 5433 -U arbitool -d arbitool_chat -t -c "SELECT COUNT(*) FROM messages WHERE processed_at IS NOT NULL;" 2>/dev/null | tr -d ' ')

    echo -e "    📊 Procesados: ${GREEN}$PROCESSED/$MSG_COUNT${NC} mensajes | Trades: ${GREEN}$TRADE_COUNT${NC} | Jobs pendientes: $JOBS"

    # Detectar si ya terminó
    if [[ "$JOBS" == "0" && "$PROCESSED" == "$MSG_COUNT" ]]; then
      echo ""
      ok "Procesamiento completo!"
      break
    fi

    # Detectar si se estancó (mismo numero de trades por 60s)
    if [[ "$TRADE_COUNT" == "$PREV_TRADES" ]]; then
      STALL_COUNT=$((STALL_COUNT + 1))
      if [[ $STALL_COUNT -ge 6 ]]; then
        echo ""
        warn "Sin cambios por 60s. Puede estar procesando un batch grande o haber terminado."
        warn "Revisar log: tail -f apps/llm-service/worker.log"
        break
      fi
    else
      STALL_COUNT=0
    fi
    PREV_TRADES=$TRADE_COUNT
  done
fi

# ── Resumen final ──
step "RESUMEN"
FINAL_MSGS=$(PGPASSWORD=arbitool psql -h localhost -p 5433 -U arbitool -d arbitool_chat -t -c "SELECT COUNT(*) FROM messages;" 2>/dev/null | tr -d ' ')
FINAL_TRADES=$(PGPASSWORD=arbitool psql -h localhost -p 5433 -U arbitool -d arbitool_chat -t -c "SELECT COUNT(*) FROM trades;" 2>/dev/null | tr -d ' ')
FINAL_PROCESSED=$(PGPASSWORD=arbitool psql -h localhost -p 5433 -U arbitool -d arbitool_chat -t -c "SELECT COUNT(*) FROM messages WHERE processed_at IS NOT NULL;" 2>/dev/null | tr -d ' ')
FINAL_GROUPS=$(PGPASSWORD=arbitool psql -h localhost -p 5433 -U arbitool -d arbitool_chat -t -c "SELECT name FROM groups;" 2>/dev/null | tr -d ' ')

echo -e "    Grupo:              ${GREEN}$FINAL_GROUPS${NC}"
echo -e "    Mensajes totales:   ${GREEN}$FINAL_MSGS${NC}"
echo -e "    Mensajes procesados:${GREEN}$FINAL_PROCESSED${NC}"
echo -e "    Trades extraidos:   ${GREEN}$FINAL_TRADES${NC}"
echo ""
echo -e "${GREEN}=== Listo! ===${NC}"

# Paso a paso: Procesar un nuevo cliente

## Forma rápida (un comando)

```bash
./scripts/nuevo-cliente.sh /ruta/al/chat.zip "Nombre del grupo"
```

Esto hace todo automáticamente:
1. Verifica que Docker esté corriendo
2. Borra datos anteriores (BD, Redis, media)
3. Importa el ZIP con los mensajes
4. Arranca el worker LLM y muestra el progreso

### Opciones

```bash
# Solo importar mensajes, sin procesar con LLM
./scripts/nuevo-cliente.sh /ruta/al/chat.zip "Nombre" --no-llm

# No borrar datos anteriores (agregar un grupo más)
./scripts/nuevo-cliente.sh /ruta/al/chat.zip "Nombre" --skip-reset
```

---

## Forma manual (paso a paso)

### Prerequisitos

- Docker instalado
- Node.js + npm
- Python 3 con venv en `apps/llm-service/venv/`
- Variables de entorno configuradas en `apps/llm-service/.env` (GEMINI_API_KEY, PROMPT_MODE, etc.)

### 1. Levantar servicios

```bash
docker compose up -d
```

Verificar que estén corriendo:
```bash
docker compose ps
```

Deberías ver `postgres` y `redis` en estado "running".

### 2. Limpiar datos anteriores

```bash
# Truncar base de datos
PGPASSWORD=arbitool psql -h localhost -p 5433 -U arbitool -d arbitool_chat -f db/truncate_all.sql

# Vaciar cola Redis
redis-cli -p 6380 DEL arbitool:llm:jobs

# Borrar media anterior
rm -rf media && mkdir -p media
```

### 3. Importar el backup ZIP

```bash
export PGPORT=5433
export REDIS_PORT=6380
npm run backup -- --file "/ruta/al/chat.zip" --group-name "Nombre del grupo"
```

Esto parsea el ZIP, extrae mensajes y media, guarda en la BD, y encola un job para el LLM.

### 4. Arrancar el worker LLM

```bash
cd apps/llm-service
./run-worker.sh
```

Ver el progreso:
```bash
tail -f apps/llm-service/worker.log
```

### 5. Verificar resultados

```bash
# Cuántos mensajes se importaron
PGPASSWORD=arbitool psql -h localhost -p 5433 -U arbitool -d arbitool_chat -c "SELECT COUNT(*) FROM messages;"

# Cuántos se procesaron
PGPASSWORD=arbitool psql -h localhost -p 5433 -U arbitool -d arbitool_chat -c "SELECT COUNT(*) FROM messages WHERE processed_at IS NOT NULL;"

# Trades extraídos
PGPASSWORD=arbitool psql -h localhost -p 5433 -U arbitool -d arbitool_chat -c "SELECT COUNT(*) FROM trades;"

# Ver detalle de trades
PGPASSWORD=arbitool psql -h localhost -p 5433 -U arbitool -d arbitool_chat -c "SELECT type, amount, currency, price_or_ref, trade_date FROM trades ORDER BY trade_date;"
```

---

## Notas

- **Puertos**: PostgreSQL usa `5433` (no el default 5432), Redis usa `6380`
- **PROMPT_MODE**: Configurar en `apps/llm-service/.env` según el tipo de chat:
  - `receipts` → Comprobantes con cotización de 4 dígitos
  - `conversational` → Chat 1-a-1 trader-cliente
- **Si el LLM falla**: Revisar `apps/llm-service/worker.log` y verificar que `GEMINI_API_KEY` esté configurada
- **Para reprocesar solo el LLM** (sin reimportar mensajes):
  ```bash
  # Resetear processed_at de los mensajes
  PGPASSWORD=arbitool psql -h localhost -p 5433 -U arbitool -d arbitool_chat -c "UPDATE messages SET processed_at = NULL; DELETE FROM trades;"

  # Encolar job manualmente
  cd apps/backup-processor
  npx tsx src/scripts/enqueue-llm-job.ts 2025-01-01 2026-12-31

  # Arrancar worker
  cd ../llm-service && ./run-worker.sh
  ```

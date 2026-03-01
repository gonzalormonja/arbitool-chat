# Arbitool Chat

Sistema para capturar mensajes de grupos de WhatsApp (compra/venta de cripto), ingestar backups y procesarlos con IA para detectar operaciones (trades).

## Arquitectura

- **Bot WhatsApp** (`apps/bot`): escucha grupos en vivo con whatsapp-web.js, persiste mensajes y media en PostgreSQL y encola trabajos para el LLM.
- **Procesador de backup** (`apps/backup-processor`): sube y parsea exportaciones .txt o .zip de WhatsApp, inserta en la misma BD y encola para el LLM.
- **Servicio LLM** (`apps/llm-service`): worker en Python que consume la cola Redis, lee mensajes no procesados, llama al LLM para extraer compras/ventas y escribe en `trades` y marca `processed_at`.

## Requisitos

- Node.js >= 18
- Python 3.12+ (para el servicio LLM)
- PostgreSQL y Redis (por ejemplo con Docker)

## Inicio rápido

1. **Levantar infraestructura**

   ```bash
   docker compose up -d
   ```

2. **Aplicar migraciones**

   ```bash
   psql -h localhost -U arbitool -d arbitool_chat -f db/migrations/001_initial.sql
   ```

3. **Instalar y compilar (monorepo)**

   ```bash
   npm install
   npm run build
   ```

4. **Bot WhatsApp** (genera QR para vincular)

   ```bash
   npm run bot
   ```

5. **Procesar un backup**

   ```bash
   node apps/backup-processor/dist/index.js --file /ruta/chat.txt --group-name "Mi grupo"
   ```

6. **Worker LLM** (requiere `OPENAI_API_KEY`)

   ```bash
   cd apps/llm-service && pip install -r requirements.txt && python -m src.main
   ```

## Variables de entorno

- `DATABASE_URL` / `PGHOST`, `PGUSER`, `PGPASSWORD`, `PGPORT`, `PGDATABASE`: PostgreSQL.
- `REDIS_HOST`, `REDIS_PORT`: Redis (cola LLM).
- `MEDIA_PATH`: carpeta donde guardar fotos/audios (bot y backup).
- `OPENAI_API_KEY`, `OPENAI_MODEL`: servicio LLM (por defecto `gpt-4o-mini`).

## Documentación

- [Formato de backup de WhatsApp](docs/backup-format.md): cómo exportar y qué formato espera el procesador.

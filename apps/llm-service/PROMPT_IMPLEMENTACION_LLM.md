# Prompt: Cómo replicar el servicio LLM de Arbitool en otro repo

Este documento describe todo lo que tiene instalado el servicio LLM de Arbitool y cómo procesa PDFs, imágenes, audios y mensajes de chat, para que puedas implementar la misma arquitectura en otro proyecto.

---

## 1. Resumen del flujo

1. **Cola de jobs**: Un worker Python consume jobs desde Redis (`arbitool:llm:jobs`). Cada job es un JSON: `{ group_id, from_date?, to_date? }`.
2. **Mensajes**: El worker obtiene de PostgreSQL mensajes no procesados (con overlap opcional para contexto entre batches).
3. **LLM**: Construye un prompt con los mensajes y, si hay adjuntos, envía **imágenes**, **PDFs** y **audios** al modelo (multimodal).
4. **Salida**: Parsea la respuesta JSON del LLM, deduplica trades por comprobante, inserta en `trades` y marca mensajes como procesados.

---

## 2. Dependencias instaladas (Python)

```
redis>=5.0.0
psycopg[binary]>=3.1.0
openai>=1.0.0
python-dotenv>=1.0.0
google-generativeai>=0.3.0
Pillow>=10.0.0
```

- **redis**: consumir jobs con `brpop(arbitool:llm:jobs)`.
- **psycopg**: leer mensajes y escribir trades en PostgreSQL.
- **openai**: cliente OpenAI-compatible (OpenAI, Groq, Ollama, etc.) para modo solo texto.
- **python-dotenv**: cargar `.env` desde el directorio del servicio.
- **google-generativeai**: **Gemini** para multimodal (imágenes + PDFs + audios).
- **Pillow**: abrir imágenes, redimensionar si son muy grandes antes de enviar al LLM.

No se usa PyPDF2 ni pdf2image: los PDFs se envían como bytes con `inline_data` a Gemini (Gemini lee PDFs nativamente).

---

## 3. Procesamiento de archivos (multimodal)

El cliente LLM (`client.py`) distingue por extensión y envía cada tipo al modelo de forma distinta.

### 3.1 Imágenes (vision)

- **Extensiones**: `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`.
- **Proceso**: Se cargan con `PIL.Image.open(path)`. Si el lado mayor > 1024 px, se redimensiona manteniendo ratio (LANCZOS). Se añaden al contenido como objetos `Image` de PIL (Gemini los acepta).
- **Uso**: Comprobantes de transferencias, capturas de pantalla, etc.

### 3.2 PDFs

- **Extensiones**: `.pdf`.
- **Límite**: 20 MB por archivo (archivos más grandes se omiten con un log).
- **Proceso**: Se lee el archivo con `path.read_bytes()` y se envía a Gemini como:
  ```python
  {"inline_data": {"mime_type": "application/pdf", "data": data}}
  ```
- **Uso**: Comprobantes en PDF. El prompt indica que cada página/PDF que muestre una transferencia es un comprobante y debe generar un trade.

### 3.3 Audios (notas de voz)

- **Extensiones**: `.ogg`, `.opus`, `.mp3`, `.m4a`, `.webm`, `.wav`, `.mp4`, `.mpeg`, `.mpga`.
- **MIME**: Se mapea cada extensión a su MIME (p. ej. `audio/ogg`, `audio/mpeg`).
- **Límite**: 20 MB por archivo.
- **Proceso**: Se lee el archivo en bytes y se envía como:
  ```python
  {"inline_data": {"mime_type": mime, "data": data}}
  ```
- **Uso**: Transcribir y usar cantidades, cotizaciones o detalles mencionados para completar o confirmar trades.

### 3.4 Texto (mensajes)

- Los mensajes se formatean en texto plano con `build_messages_prompt(messages)`: por cada mensaje una línea tipo `[ID:123] [fecha] Sender: contenido [ATTACHMENT: /path]`.
- Ese texto va siempre en el prompt; si hay imágenes/PDF/audio, se añaden después con etiquetas del tipo "Image for message ID: 123", "PDF for message ID: 456", "Audio for message ID: 789", para que el modelo correlacione con el chat.

### 3.5 XLSX / CSV (tablas) — subir como archivo

- **CSV: sí, como archivo.** Gemini acepta `text/csv` en `inline_data`. Puedes leer el archivo y enviarlo tal cual, sin pandas:
  ```python
  data = Path(csv_path).read_bytes()
  content_parts.append({"inline_data": {"mime_type": "text/csv", "data": data}})
  ```
  Etiqueta igual que con PDF/audio, p. ej.: `"CSV for message ID: 123 (path: ...)"`.

- **XLSX: no como archivo.** La API de Gemini no soporta el MIME de Excel (`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`). Si subes el binario, suele responder con error de tipo no soportado. Para XLSX hay que convertirlo antes a CSV (o a texto) y luego:
  - o bien enviar ese CSV **como archivo** con `mime_type: "text/csv"` (leyendo el string en bytes),
  - o bien meter el texto en el prompt.
  La conversión XLSX → CSV la puedes hacer con pandas (`read_excel` + `to_csv`) o con openpyxl leyendo celdas y generando el string CSV.

- **¿Qué da mejor resultado: texto de pandas (df.to_string()) o CSV?**  
  **CSV** suele dar mejor resultado: es estándar, compacto, sin columna de índice ni alineación que añada ruido, y Gemini tiene soporte explícito para `text/csv`. Con `df.to_string()` el modelo ve índices (0, 1, 2…), espacios extra y a veces formato de números distinto. Recomendación: convertir a CSV (p. ej. `df.to_csv(index=False)`) y enviar ese CSV como archivo o como texto en el prompt.

- **Resumen**: CSV = subir el archivo con `inline_data` + `text/csv`. XLSX = no se puede subir como archivo; convertir a CSV (o texto) y después enviar ese resultado como archivo CSV o como texto.

---

## 4. Proveedores de LLM

- **Gemini (recomendado para multimodal)**: Si existe `GEMINI_API_KEY`, se usa Gemini. Soporta texto + imágenes + PDFs + audio en una sola llamada. Modelo por defecto: `gemini-2.0-flash` (configurable con `GEMINI_MODEL`).
- **OpenAI-compatible (solo texto)**: Si no hay `GEMINI_API_KEY`, se usa el cliente OpenAI con `OPENAI_API_KEY` y opcionalmente `OPENAI_BASE_URL`. Modelo por defecto: `gpt-4o-mini` (`OPENAI_MODEL`). En este flujo no se envían imágenes/PDF/audio; solo el texto de los mensajes.

---

## 5. Variables de entorno

| Variable | Uso |
|----------|-----|
| `DATABASE_URL` | PostgreSQL (mensajes y trades). |
| `REDIS_HOST`, `REDIS_PORT` | Redis para la cola de jobs. |
| `GEMINI_API_KEY` | Si está definida, se usa Gemini (multimodal). |
| `GEMINI_MODEL` | Modelo Gemini (default: `gemini-2.0-flash`). |
| `OPENAI_API_KEY`, `OPENAI_BASE_URL` | Fallback OpenAI-compatible (solo texto). |
| `OPENAI_MODEL` | Modelo para el fallback (default: `gpt-4o-mini`). |
| `PROMPT_MODE` | `receipts` (comprobantes + cotización) o `conversational` (chat trader–cliente, 1 comprobante = 1 trade). |
| `LLM_BATCH_SIZE` | Mensajes por batch (default 50). |
| `LLM_BATCH_OVERLAP` | Mensajes de solapamiento con el batch anterior para contexto (default 15). |
| `LLM_PARALLEL_WORKERS` | Batches procesados en paralelo (default 3). |
| `LLM_POLL_TIMEOUT` | Segundos de espera en `brpop` (default 30). |
| `LLM_SINGLE_BATCH` | Si `1`/`true`, un solo batch con todos los mensajes del job (útil para chats pequeños). |

---

## 6. Formato de mensajes (entrada desde tu BD)

Cada mensaje que el worker lee de la BD debe ser un dict con al menos:

- `id`: int (ID del mensaje).
- `content`: texto del mensaje (puede ser vacío).
- `message_date`: fecha/hora del mensaje.
- `media_path`: ruta absoluta o relativa al archivo adjunto (imagen, PDF, audio), o `None`.
- `sender_name`: nombre del remitente (o similar).

El worker usa `media_path` para:
- Detectar imágenes por extensión y añadirlas al contenido multimodal.
- Detectar PDFs y enviarlos como `inline_data` con MIME `application/pdf`.
- Detectar audios y enviarlos como `inline_data` con el MIME correspondiente.

---

## 7. Formato de salida del LLM (trades)

El modelo devuelve **solo** un JSON array de objetos. Cada objeto representa un trade, con campos como:

- `type`: `"buy"` o `"sell"`.
- `fiat_amount`, `fiat_currency` (p. ej. ARS).
- `amount`, `currency` (p. ej. USDT).
- `cotizacion` o `price_or_ref`.
- `trade_date`: string `YYYY-MM-DD HH:MM:SS`.
- `message_ids`: lista de IDs de mensajes relacionados.
- `comprobante_media_path`: path del comprobante (imagen o PDF) para ese trade.
- Opcionales: `bank`, `sender_name`, `cbu`, `transaction_id`, `id_colesa`, `comprobante_extra`.

El worker:
- Parsea el JSON (quitando markdown ``` si viene envuelto).
- Si la respuesta está truncada, intenta recuperar el último objeto completo antes del corte.
- Deduplica por `comprobante_media_path` (o por `no_img|{amount}` si no hay comprobante).
- Inserta cada trade nuevo en la tabla `trades` y marca los `message_ids` como procesados.

---

## 8. Cola de jobs (Redis)

- **Key**: `arbitool:llm:jobs` (o la que uses en tu repo).
- **Operación**: Quien encola hace `LPUSH key JSON.stringify(payload)`. El worker hace `BRPOP key timeout`.
- **Payload**: `{ "group_id": number, "from_date": string ISO opcional, "to_date": string ISO opcional }`.

Tu otro repo puede encolar jobs igual: mismo payload y mismo key (o una key equivalente en tu Redis).

---

## 9. Base de datos (PostgreSQL)

- **Mensajes**: tabla con al menos `id`, `group_id`, `content`, `message_type`, `media_path`, `message_date`, `processed_at`, y forma de obtener `sender_name` (p. ej. JOIN con participantes).
- **Trades**: tabla donde se insertan `group_id`, `type`, `amount`, `currency`, `price_or_ref`, `message_ids`, `comprobante_media_path`, `raw_llm_response`, `trade_date`, y campos opcionales como `bank`, `sender_name`, `cbu`, `transaction_id`, `id_colesa`, `comprobante_extra`.
- **Procesado**: el worker actualiza `processed_at = NOW()` en los mensajes que ya procesó para no repetirlos.

---

## 10. Cómo implementarlo en otro repo (checklist)

1. **Python 3.10+** y `requirements.txt` con: redis, psycopg, openai, python-dotenv, google-generativeai, Pillow.
2. **Cargar `.env`** desde el directorio del servicio (como en `main.py` con `Path(__file__).resolve().parent.parent / ".env"`).
3. **Worker de cola**: bucle que haga `brpop` a la key de jobs, deserialice el payload, llame a tu función que obtiene mensajes, llama al LLM y escribe trades.
4. **Cliente LLM**:
   - Si tienes `GEMINI_API_KEY`: para cada batch, construir lista de partes (texto + imágenes PIL + `inline_data` para PDFs y audios), llamar a `model.generate_content(parts)`.
   - Imágenes: PIL, redimensionar si max(lado) > 1024, añadir con etiqueta de message ID.
   - PDFs: leer bytes, añadir `{"inline_data": {"mime_type": "application/pdf", "data": data}}` con etiqueta de message ID.
   - Audios: leer bytes, MIME por extensión, mismo `inline_data`.
5. **Prompts**: dos modos (receipts vs conversational) según `PROMPT_MODE`; en ambos dejar muy claro que cada comprobante (imagen o PDF) = un trade y que debe devolver **solo** un JSON array.
6. **Parseo de respuesta**: quitar ``` si existe, `json.loads`; si falla y hay truncado, recuperar último objeto completo y cerrar el array.
7. **Deduplicación e inserción**: por `comprobante_media_path` (o fallback), insertar en `trades` y marcar mensajes procesados.
8. **Batch con overlap**: si quieres contexto entre batches, al traer mensajes no procesados trae también los últimos N ya procesados (ordenados por fecha) y marca solo los no procesados al terminar.

Con esto puedes replicar en otro repo el mismo flujo: cola Redis → mensajes con `media_path` → multimodal (imágenes + PDFs + audios) con Gemini → JSON de trades → guardado y marcado de procesado.

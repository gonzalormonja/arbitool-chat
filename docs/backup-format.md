# Formato de backup de WhatsApp

Este documento describe el formato esperado de los archivos de backup de WhatsApp que el **procesador de backup** puede ingestar.

## Export nativo de WhatsApp (recomendado)

### Cómo exportar desde la app

1. Abre la conversación o grupo en WhatsApp.
2. Menú (⋮) → **Más** → **Exportar chat**.
3. Elige:
   - **Sin archivos adjuntos**: se genera solo un archivo `.txt`.
   - **Incluir archivos adjuntos**: se genera un `.zip` que contiene el `.txt` y una carpeta con las fotos, audios, etc.

### Formato del archivo .txt

El archivo es UTF-8. Cada línea de mensaje sigue este patrón:

```
[DD/MM/AAAA, H:MM:SS] Nombre del contacto: Texto del mensaje
```

Ejemplos:

```
[21/02/2025, 10:30:00] Juan Pérez: Hola, vendo 100 USDT
[21/02/2025, 10:31:15] María García: image omitted
[21/02/2025, 10:32:00] You: Compro, te hablo al privado
```

- **Fecha/hora**: entre corchetes, formato `DD/MM/AAAA, H:MM:SS` (una o dos cifras para hora).
- **Nombre del contacto**: quien envía el mensaje. Si eres tú, puede aparecer como **You** (en inglés) según la configuración del teléfono.
- **Texto**: el contenido. Si en la exportación eligiste “sin archivos”, los medios aparecen como:
  - `image omitted`
  - `audio omitted`
  - `sticker omitted`
  - `video omitted`
  - `document omitted`

### Formato del ZIP (con media)

- El ZIP debe contener al menos un archivo `.txt` con el chat en el formato anterior.
- Los archivos de media (imágenes, audios, etc.) pueden estar en la raíz del ZIP o en una subcarpeta.
- Extensiones de media soportadas: `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`, `.mp4`, `.ogg`, `.mp3`, `.m4a`, `.webm`.
- La correlación “mensaje X = archivo Y” se hace **por orden de aparición**: el primer “image omitted” se asocia al primer archivo de imagen encontrado en el ZIP, y así sucesivamente.

### Límites del export nativo

- **Solo texto**: hasta ~40.000 mensajes.
- **Con media**: hasta ~10.000 mensajes.
- Los mensajes van en orden cronológico.

## Uso del procesador de backup

Desde la raíz del monorepo (o desde `apps/backup-processor`):

**Archivo .txt:**

```bash
node apps/backup-processor/dist/index.js --file /ruta/al/chat.txt --group-name "Nombre del grupo"
```

**Archivo .zip:**

```bash
node apps/backup-processor/dist/index.js --file /ruta/al/chat.zip --group-name "Nombre del grupo"
```

Opciones:

- `--file`: ruta al `.txt` o `.zip` (obligatorio).
- `--group-name`: nombre del grupo/chat para mostrar (obligatorio).
- `--group-id`: identificador externo del grupo en la BD. Por defecto se genera uno a partir del nombre (ej. `backup-nombre-del-grupo`).
- `--self-name`: nombre con el que reemplazar "You" en el export (opcional).

Después de ingestar, los mensajes se guardan en la base de datos con `source = 'backup'` y se encola un trabajo para que el **servicio LLM** procese y detecte compras/ventas.

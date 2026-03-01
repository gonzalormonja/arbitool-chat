import * as fs from 'node:fs';
import * as path from 'node:path';
import unzipper from 'unzipper';
import { parseTxtStream, type ParsedLine } from './txt.js';
import { MESSAGE_TYPE } from '@arbitool/shared';

export interface ParsedEntry extends ParsedLine {
  media_path?: string | null;
}

export interface BackupResult {
  entries: ParsedEntry[];
  tempDir?: string;
}

const MEDIA_EXT = /\.(jpg|jpeg|png|gif|webp|mp4|ogg|mp3|m4a|webm)$/i;

/**
 * Extract ZIP to a directory, then parse the .txt and correlate media by order.
 * Media files are copied to mediaDir. Temp dir is removed after parse.
 */
export async function parseZip(
  zipPath: string,
  mediaDir: string
): Promise<BackupResult> {
  const tempDir = path.join(mediaDir, `backup_${Date.now()}`);
  await fs.promises.mkdir(tempDir, { recursive: true });
  await fs.promises.mkdir(mediaDir, { recursive: true });

  await new Promise<void>((resolve, reject) => {
    fs.createReadStream(zipPath)
      .pipe(unzipper.Extract({ path: tempDir }))
      .on('close', resolve)
      .on('error', reject);
  });

  const mediaByOrder: string[] = [];
  let txtPath: string | null = null;

  async function walk(dir: string, base = ''): Promise<void> {
    const entries = await fs.promises.readdir(dir, { withFileTypes: true });
    for (const e of entries) {
      const rel = path.join(base, e.name);
      const full = path.join(dir, e.name);
      if (e.isDirectory()) await walk(full, rel);
      else if (e.name.endsWith('.txt')) txtPath = full;
      else if (MEDIA_EXT.test(e.name)) {
        const outName = `backup_${mediaByOrder.length}${path.extname(e.name)}`;
        const outPath = path.join(mediaDir, outName);
        await fs.promises.copyFile(full, outPath);
        mediaByOrder.push(outPath);
      }
    }
  }

  await walk(tempDir);

  if (!txtPath) {
    await fs.promises.rm(tempDir, { recursive: true, force: true });
    return { entries: [] };
  }

  const entries: ParsedEntry[] = [];
  let mediaIndex = 0;
  const stream = fs.createReadStream(txtPath, { encoding: 'utf8' });
  for await (const line of parseTxtStream(stream)) {
    const entry: ParsedEntry = { ...line };
    const isMedia = line.message_type !== MESSAGE_TYPE.TEXT;
    if (isMedia && mediaIndex < mediaByOrder.length) {
      entry.media_path = mediaByOrder[mediaIndex]!;
      mediaIndex++;
    }
    entries.push(entry);
  }

  await fs.promises.rm(tempDir, { recursive: true, force: true });
  return { entries };
}

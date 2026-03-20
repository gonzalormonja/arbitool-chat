import pg from 'pg';
import { createHash } from 'node:crypto';
import { config } from './config.js';
import { enqueueLlmProcess } from './queue.js';
import { MESSAGE_SOURCE, type MessageInsert } from '@arbitool/shared';
import type { ParsedEntry } from './parser/zip.js';

const pool = new pg.Pool(config.database);

function contentHash(content: string): string {
  return createHash('sha256').update(content).digest('hex');
}

export async function getOrCreateGroup(
  externalId: string,
  name: string
): Promise<number> {
  const client = await pool.connect();
  try {
    const sel = await client.query(
      'SELECT id FROM groups WHERE external_id = $1',
      [externalId]
    );
    if (sel.rows.length > 0) return sel.rows[0].id;
    const ins = await client.query(
      'INSERT INTO groups (external_id, name) VALUES ($1, $2) RETURNING id',
      [externalId, name]
    );
    return ins.rows[0].id;
  } finally {
    client.release();
  }
}

export async function getOrCreateParticipant(
  groupId: number,
  externalId: string,
  displayName: string
): Promise<number> {
  const client = await pool.connect();
  try {
    const sel = await client.query(
      'SELECT id FROM participants WHERE group_id = $1 AND external_id = $2',
      [groupId, externalId]
    );
    if (sel.rows.length > 0) return sel.rows[0].id;
    const ins = await client.query(
      'INSERT INTO participants (group_id, external_id, display_name) VALUES ($1, $2, $3) RETURNING id',
      [groupId, externalId, displayName]
    );
    return ins.rows[0].id;
  } finally {
    client.release();
  }
}

export async function insertMessagesBatch(
  groupId: number,
  entries: ParsedEntry[],
  participantIdByKey: Map<string, number>
): Promise<number[]> {
  if (entries.length === 0) return [];
  const ids: number[] = [];
  const client = await pool.connect();
  try {
    for (const e of entries) {
      const key = `${groupId}:${e.sender_name}`;
      const senderId = participantIdByKey.get(key) ?? null;
      const hash = e.content ? contentHash(e.content) : null;
      const msg: MessageInsert = {
        group_id: groupId,
        sender_id: senderId,
        external_id: null,
        content: e.content,
        message_type: e.message_type,
        media_path: e.media_path ?? null,
        raw_payload: { source: 'backup' },
        source: MESSAGE_SOURCE.BACKUP,
        message_date: e.message_date,
        content_hash: hash,
      };
      const r = await client.query(
        `INSERT INTO messages (
          group_id, sender_id, external_id, content, message_type, media_path,
          raw_payload, source, message_date, content_hash
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10) RETURNING id`,
        [
          msg.group_id,
          msg.sender_id ?? null,
          msg.external_id ?? null,
          msg.content,
          msg.message_type,
          msg.media_path ?? null,
          msg.raw_payload ? JSON.stringify(msg.raw_payload) : null,
          msg.source,
          msg.message_date,
          msg.content_hash ?? null,
        ]
      );
      ids.push(r.rows[0].id);
    }
  } finally {
    client.release();
  }
  return ids;
}

export async function closeDb(): Promise<void> {
  await pool.end();
}

export type PersistBackupOptions = {
  /** If true, do not enqueue the LLM job (only insert messages). */
  skipLlm?: boolean;
};

export async function persistBackup(
  groupExternalId: string,
  groupName: string,
  entries: ParsedEntry[],
  options?: PersistBackupOptions
): Promise<{ groupId: number; messageIds: number[] }> {
  const groupId = await getOrCreateGroup(groupExternalId, groupName);
  const participantKey = new Map<string, number>();

  for (const e of entries) {
    const key = `${groupId}:${e.sender_name}`;
    if (!participantKey.has(key)) {
      const pid = await getOrCreateParticipant(
        groupId,
        e.sender_name,
        e.sender_name
      );
      participantKey.set(key, pid);
    }
  }

  const batchSize = config.batchSize;
  const allIds: number[] = [];
  for (let i = 0; i < entries.length; i += batchSize) {
    const batch = entries.slice(i, i + batchSize);
    const ids = await insertMessagesBatch(groupId, batch, participantKey);
    allIds.push(...ids);
  }

  if (entries.length > 0 && !options?.skipLlm) {
    // Find min and max date across ALL entries, not just first/last
    let minDate = entries[0]!.message_date;
    let maxDate = entries[0]!.message_date;
    for (const e of entries) {
      if (e.message_date < minDate) minDate = e.message_date;
      if (e.message_date > maxDate) maxDate = e.message_date;
    }

    const payload = {
      group_id: groupId,
      from_date: minDate.toISOString(),
      to_date: maxDate.toISOString(),
    };

    console.log(`Enqueuing LLM job for group ${groupId}:`, payload);
    await enqueueLlmProcess(payload);
  }

  return { groupId, messageIds: allIds };
}

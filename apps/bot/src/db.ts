import pg from 'pg';
import { config } from './config.js';
import type { MessageInsert } from '@arbitool/shared';
import { MESSAGE_SOURCE } from '@arbitool/shared';

const pool = new pg.Pool(config.database);

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

export async function insertMessage(msg: MessageInsert): Promise<number> {
  const r = await pool.query(
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
  return r.rows[0].id;
}

export async function closeDb(): Promise<void> {
  await pool.end();
}

import type { Message } from 'whatsapp-web.js';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { createHash } from 'node:crypto';
import { config } from '../config.js';
import { getOrCreateGroup, getOrCreateParticipant, insertMessage } from '../db.js';
import { enqueueLlmProcess } from '../queue.js';
import {
  MESSAGE_TYPE,
  MESSAGE_SOURCE,
  type MessageType,
} from '@arbitool/shared';

const MEDIA_OMITTED_PATTERNS: Record<string, MessageType> = {
  'image omitted': MESSAGE_TYPE.IMAGE,
  'audio omitted': MESSAGE_TYPE.AUDIO,
  'sticker omitted': MESSAGE_TYPE.STICKER,
  'video omitted': 'video' as MessageType,
  'document omitted': 'document' as MessageType,
};

function ensureMediaDir(): string {
  const dir = path.resolve(config.mediaPath);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  return dir;
}

function contentHash(content: string): string {
  return createHash('sha256').update(content).digest('hex');
}

function inferMessageType(body: string, hasMedia: boolean): MessageType {
  const lower = body.trim().toLowerCase();
  for (const [key, type] of Object.entries(MEDIA_OMITTED_PATTERNS)) {
    if (lower === key) return type;
  }
  if (hasMedia) return MESSAGE_TYPE.IMAGE; // fallback for live media
  return MESSAGE_TYPE.TEXT;
}

export async function handleMessage(msg: Message): Promise<void> {
  const chat = await msg.getChat();
  if (!chat.isGroup) return;

  const groupIdW = chat.id._serialized;
  const groupName = chat.name ?? groupIdW;

  const groupId = await getOrCreateGroup(groupIdW, groupName);

  const contact = await msg.getContact();
  const senderExternalId = (msg as { author?: string }).author ?? contact.id._serialized;
  const senderName = contact.pushname ?? contact.number ?? senderExternalId;

  const participantId = await getOrCreateParticipant(
    groupId,
    senderExternalId,
    senderName
  );

  let content = msg.body ?? '';
  let messageType = inferMessageType(content, msg.hasMedia);
  let mediaPath: string | null = null;
  const rawPayload: Record<string, unknown> = {
    from: msg.from,
    id: msg.id?.id,
    timestamp: msg.timestamp,
  };

  if (msg.hasMedia) {
    try {
      const media = await msg.downloadMedia();
      if (media) {
        const ext = media.mimetype?.split('/')[1] ?? 'bin';
        const safeId = (msg.id?.id ?? String(Date.now())).replace(/\D/g, '');
        const dir = ensureMediaDir();
        const filename = `${groupId}_${safeId}.${ext}`;
        const filepath = path.join(dir, filename);
        const buf = Buffer.from(media.data, 'base64');
        fs.writeFileSync(filepath, buf);
        mediaPath = path.relative(process.cwd(), filepath);
        if (media.mimetype?.startsWith('image/')) messageType = MESSAGE_TYPE.IMAGE;
        else if (media.mimetype?.startsWith('audio/')) messageType = MESSAGE_TYPE.AUDIO;
        else if (media.mimetype?.includes('webp')) messageType = MESSAGE_TYPE.STICKER;
      }
    } catch (e) {
      rawPayload.mediaError = String(e);
      if (content === '') content = '[media download failed]';
    }
  }

  const messageDate = new Date((msg.timestamp ?? 0) * 1000);
  const hash = content ? contentHash(content) : null;

  await insertMessage({
    group_id: groupId,
    sender_id: participantId,
    external_id: msg.id?.id ?? null,
    content,
    message_type: messageType,
    media_path: mediaPath,
    raw_payload: rawPayload,
    source: MESSAGE_SOURCE.LIVE,
    message_date: messageDate,
    content_hash: hash,
  });

  // Optional: enqueue for LLM periodically (e.g. every N messages per group)
  // Here we enqueue a job for this group so the LLM worker can process recent unprocessed messages
  if (config.enqueueLlmAfterMessages > 0) {
    await enqueueLlmProcess({
      group_id: groupId,
      from_date: messageDate.toISOString(),
      to_date: messageDate.toISOString(),
    });
  }
}

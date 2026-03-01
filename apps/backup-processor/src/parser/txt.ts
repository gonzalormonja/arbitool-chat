import { createReadStream } from 'node:fs';
import { createInterface } from 'node:readline';
import type { Readable } from 'node:stream';
import { MESSAGE_TYPE, type MessageType } from '@arbitool/shared';

export interface ParsedLine {
  message_date: Date;
  sender_name: string;
  content: string;
  message_type: MessageType;
}

const LINE_REGEX =
  /^\[(\d{1,2}\/\d{1,2}\/\d{4}),\s*(\d{1,2}:\d{2}:\d{2})\]\s*([^:]+):\s*(.*)$/;

const OMITTED_TO_TYPE: Record<string, MessageType> = {
  'image omitted': MESSAGE_TYPE.IMAGE,
  'audio omitted': MESSAGE_TYPE.AUDIO,
  'sticker omitted': MESSAGE_TYPE.STICKER,
  'video omitted': 'video' as MessageType,
  'document omitted': 'document' as MessageType,
};

function parseDate(dateStr: string, timeStr: string): Date {
  const [d, m, y] = dateStr.split('/').map(Number);
  const [h, min, s] = timeStr.split(':').map(Number);
  return new Date(y, m - 1, d, h, min, s);
}

function inferMessageType(content: string): MessageType {
  const lower = content.trim().toLowerCase();
  return OMITTED_TO_TYPE[lower] ?? MESSAGE_TYPE.TEXT;
}

export async function* parseTxtStream(
  input: Readable | string,
  options: { selfName?: string } = {}
): AsyncGenerator<ParsedLine> {
  const stream =
    typeof input === 'string'
      ? createReadStream(input, { encoding: 'utf8' })
      : input;
  const rl = createInterface({ input: stream, crlfDelay: Infinity });
  const selfName = options.selfName ?? 'You';

  for await (const line of rl) {
    const trimmed = line.trim();
    if (!trimmed) continue;

    const match = trimmed.match(LINE_REGEX);
    if (!match) continue;

    const [, dateStr, timeStr, sender, content] = match;
    const message_date = parseDate(dateStr!, timeStr!);
    const sender_name = sender!.trim() === 'You' ? selfName : sender!.trim();
    const message_type = inferMessageType(content ?? '');

    yield {
      message_date,
      sender_name,
      content: (content ?? '').trim(),
      message_type,
    };
  }
}

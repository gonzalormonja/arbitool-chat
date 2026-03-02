import { createReadStream } from 'node:fs';
import { createInterface } from 'node:readline';
import type { Readable } from 'node:stream';
import { MESSAGE_TYPE, type MessageType } from '@arbitool/shared';

export interface ParsedLine {
  message_date: Date;
  sender_name: string;
  content: string;
  message_type: MessageType;
  attachment_name?: string;
}

const LINE_REGEX =
  /^\[(\d{1,2}\/\d{1,2}\/\d{2,4}),\s*(\d{1,2}:\d{2}:\d{2})\]\s*([^:]+):\s*(.*)$/;

const ATTACHMENT_REGEX = /<adjunto:\s*([^>]+)>/;

const OMITTED_TO_TYPE: Record<string, MessageType> = {
  'image omitted': MESSAGE_TYPE.IMAGE,
  'audio omitted': MESSAGE_TYPE.AUDIO,
  'sticker omitted': MESSAGE_TYPE.STICKER,
  'video omitted': 'video' as MessageType,
  'document omitted': 'document' as MessageType,
};

function parseDate(dateStr: string, timeStr: string): Date {
  let [d, m, y] = dateStr.split('/').map(Number);
  if (y < 100) y += 2000;
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

  let currentEntry: ParsedLine | null = null;

  for await (const line of rl) {
    const trimmed = line.trim();
    // Allow empty lines within multiline messages if needed, but usually we just append
    
    const match = trimmed.match(LINE_REGEX);
    if (match) {
      // If we have a pending entry, yield it before starting a new one
      if (currentEntry) {
        yield currentEntry;
      }

      const [, dateStr, timeStr, sender, content] = match;
      const message_date = parseDate(dateStr!, timeStr!);
      const sender_name = sender!.trim() === 'You' ? selfName : sender!.trim();
      
      let finalContent = (content ?? '').trim();
      let attachment_name: string | undefined;
      
      // Check for attachment
      const attachMatch = finalContent.match(ATTACHMENT_REGEX);
      if (attachMatch) {
        attachment_name = attachMatch[1].trim();
        finalContent = finalContent.replace(ATTACHMENT_REGEX, '').trim();
      }

      let message_type = inferMessageType(finalContent);
      if (attachment_name) {
         if (/\.(jpg|jpeg|png|gif|webp)$/i.test(attachment_name)) message_type = MESSAGE_TYPE.IMAGE;
         else if (/\.(mp3|ogg|wav|m4a)$/i.test(attachment_name)) message_type = MESSAGE_TYPE.AUDIO;
         else if (/\.(mp4|webm|mov)$/i.test(attachment_name)) message_type = 'video' as MessageType;
         else message_type = 'document' as MessageType;
      }

      currentEntry = {
        message_date,
        sender_name,
        content: finalContent,
        message_type,
        attachment_name,
      };
    } else if (currentEntry) {
      // Multiline message: append this line to the current entry's content
      // Preserve the newline structure implicitly by joining with \n
      currentEntry.content += '\n' + line; 
    }
  }

  // Yield the last entry if exists
  if (currentEntry) {
    yield currentEntry;
  }
}

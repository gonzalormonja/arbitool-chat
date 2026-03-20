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

// Format 1: [20/1/25, 14:11:16] Sender: message (D/M/Y 24h)
// Format 2: [1/3/26 上午12:21:33] Sender: message (Chinese AM/PM)
// Format 3: [15/1/26, 12:07:25 p. m.] Sender: message (Spanish AM/PM)
// Format 4: [2026/1/14 15:47:12] Sender: message (Y/M/D 24h, no comma)
const LINE_REGEX_STANDARD =
  /^\[(\d{1,2}\/\d{1,2}\/\d{2,4}),\s*(\d{1,2}:\d{2}:\d{2})\]\s*([^:]+):\s*(.*)$/;

const LINE_REGEX_SPANISH_AMPM =
  /^\[(\d{1,2}\/\d{1,2}\/\d{2,4}),\s*(\d{1,2}:\d{2}:\d{2})\s*(a\.\s*m\.|p\.\s*m\.)\]\s*([^:]+):\s*(.*)$/;

const LINE_REGEX_CHINESE =
  /^\[(\d{1,2}\/\d{1,2}\/\d{2,4})\s*(上午|下午)?(\d{1,2}:\d{2}:\d{2})\]\s*([^:]+):\s*(.*)$/;

const LINE_REGEX_YMD =
  /^\[(\d{4}\/\d{1,2}\/\d{1,2})\s+(\d{1,2}:\d{2}:\d{2})\]\s*([^:]+):\s*(.*)$/;

// Attachment patterns: Spanish and Chinese
const ATTACHMENT_REGEX = /<adjunto:\s*([^>]+)>/;
const ATTACHMENT_REGEX_CHINESE = /<附件[：:]\s*([^>]+)>/;

const OMITTED_TO_TYPE: Record<string, MessageType> = {
  'image omitted': MESSAGE_TYPE.IMAGE,
  'audio omitted': MESSAGE_TYPE.AUDIO,
  'sticker omitted': MESSAGE_TYPE.STICKER,
  'video omitted': 'video' as MessageType,
  'document omitted': 'document' as MessageType,
  // Chinese equivalents
  '图像已忽略': MESSAGE_TYPE.IMAGE,
  '音频已忽略': MESSAGE_TYPE.AUDIO,
  '贴图已忽略': MESSAGE_TYPE.STICKER,
  '视频已忽略': 'video' as MessageType,
  '文档已忽略': 'document' as MessageType,
};

function parseDate(dateStr: string, timeStr: string, ampm?: string): Date {
  const parts = dateStr.split('/').map(Number);
  let d: number, m: number, y: number;
  // Detect Y/M/D format (first part is 4 digits = year)
  if (parts[0] > 100) {
    [y, m, d] = parts;
  } else {
    [d, m, y] = parts;
    if (y < 100) y += 2000;
  }
  let [h, min, s] = timeStr.split(':').map(Number);
  
  // Handle AM/PM: Chinese (上午/下午) or Spanish (a. m./p. m.)
  if (ampm) {
    const isPM = ampm === '下午' || ampm.startsWith('p');
    const isAM = ampm === '上午' || ampm.startsWith('a');
    if (isPM && h < 12) h += 12;
    else if (isAM && h === 12) h = 0;
  }
  
  return new Date(y, m - 1, d, h, min, s);
}

function inferMessageType(content: string): MessageType {
  const trimmed = content.trim();
  return OMITTED_TO_TYPE[trimmed.toLowerCase()] ?? OMITTED_TO_TYPE[trimmed] ?? MESSAGE_TYPE.TEXT;
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
    // Remove invisible Unicode chars that WhatsApp sometimes adds
    const trimmed = line.replace(/[\u200e\u200f\u202a-\u202e]/g, '').trim();
    
    // Try Spanish AM/PM first (most specific), then standard 24h, then Chinese
    let match = trimmed.match(LINE_REGEX_SPANISH_AMPM);
    let dateStr: string | undefined;
    let timeStr: string | undefined;
    let ampm: string | undefined;
    let sender: string | undefined;
    let content: string | undefined;

    if (match) {
      [, dateStr, timeStr, ampm, sender, content] = match;
    } else {
      match = trimmed.match(LINE_REGEX_YMD);
      if (match) {
        [, dateStr, timeStr, sender, content] = match;
      } else {
        match = trimmed.match(LINE_REGEX_STANDARD);
        if (match) {
          [, dateStr, timeStr, sender, content] = match;
        } else {
          match = trimmed.match(LINE_REGEX_CHINESE);
          if (match) {
            [, dateStr, ampm, timeStr, sender, content] = match;
          }
        }
      }
    }
    
    if (match && dateStr && timeStr && sender !== undefined) {
      // If we have a pending entry, yield it before starting a new one
      if (currentEntry) {
        yield currentEntry;
      }

      const message_date = parseDate(dateStr, timeStr, ampm);
      const sender_name = sender.trim() === 'You' ? selfName : sender.trim();
      
      let finalContent = (content ?? '').trim();
      let attachment_name: string | undefined;
      
      // Check for attachment (Spanish or Chinese format)
      let attachMatch = finalContent.match(ATTACHMENT_REGEX);
      if (!attachMatch) {
        attachMatch = finalContent.match(ATTACHMENT_REGEX_CHINESE);
      }
      if (attachMatch) {
        attachment_name = attachMatch[1].trim();
        finalContent = finalContent.replace(ATTACHMENT_REGEX, '').replace(ATTACHMENT_REGEX_CHINESE, '').trim();
      }

      let message_type = inferMessageType(finalContent);
      if (attachment_name) {
         if (/\.(jpg|jpeg|png|gif|webp)$/i.test(attachment_name)) message_type = MESSAGE_TYPE.IMAGE;
         else if (/\.(mp3|ogg|opus|wav|m4a|webm)$/i.test(attachment_name)) message_type = MESSAGE_TYPE.AUDIO;
         else if (/\.(mp4|mov)$/i.test(attachment_name)) message_type = 'video' as MessageType;
         else if (/\.pdf$/i.test(attachment_name)) message_type = 'document' as MessageType;
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
      const appendLine = line.replace(/[\u200e\u200f\u202a-\u202e]/g, '').trim();
      currentEntry.content += '\n' + appendLine;
      // Attachment can appear on a following line (e.g. "Comprobante.pdf • 1 página" then "<adjunto: ...>" or "audio omitted" then "<adjunto: file.opus>")
      if (!currentEntry.attachment_name) {
        const attachMatch = appendLine.match(ATTACHMENT_REGEX) ?? appendLine.match(ATTACHMENT_REGEX_CHINESE);
        if (attachMatch) {
          currentEntry.attachment_name = attachMatch[1].trim();
          const an = currentEntry.attachment_name;
          if (/\.(jpg|jpeg|png|gif|webp)$/i.test(an)) currentEntry.message_type = MESSAGE_TYPE.IMAGE;
          else if (/\.(mp3|ogg|opus|wav|m4a|webm)$/i.test(an)) currentEntry.message_type = MESSAGE_TYPE.AUDIO;
          else if (/\.(mp4|mov)$/i.test(an)) currentEntry.message_type = 'video' as MessageType;
          else if (/\.pdf$/i.test(an)) currentEntry.message_type = 'document' as MessageType;
        }
      }
    }
  }

  // Yield the last entry if exists
  if (currentEntry) {
    yield currentEntry;
  }
}

import type { MessageType, MessageSource, TradeType } from './constants.js';

export interface Group {
  id: number;
  external_id: string;
  name: string;
  created_at: Date;
  updated_at: Date;
}

export interface Participant {
  id: number;
  group_id: number;
  external_id: string;
  display_name: string;
  first_seen_at: Date;
}

export interface Message {
  id: number;
  group_id: number;
  sender_id: number | null;
  external_id: string | null;
  content: string;
  message_type: MessageType;
  media_path: string | null;
  raw_payload: Record<string, unknown> | null;
  source: MessageSource;
  message_date: Date;
  created_at: Date;
  processed_at: Date | null;
}

export interface MessageInsert {
  group_id: number;
  sender_id?: number | null;
  external_id?: string | null;
  content: string;
  message_type: MessageType;
  media_path?: string | null;
  raw_payload?: Record<string, unknown> | null;
  source: MessageSource;
  message_date: Date;
  content_hash?: string | null;
}

export interface Trade {
  id: number;
  group_id: number;
  type: TradeType;
  amount: number | null;
  currency: string | null;
  price_or_ref: string | null;
  message_ids: number[];
  comprobante_media_path: string | null;
  raw_llm_response: Record<string, unknown> | null;
  created_at: Date;
}

export interface MessageBatch {
  id: number;
  group_id: number;
  status: string;
  created_at: Date;
  updated_at: Date;
}

export interface LlmProcessJobPayload {
  group_id: number;
  message_ids?: number[];
  from_date?: string;
  to_date?: string;
}

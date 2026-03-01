export const MESSAGE_TYPE = {
  TEXT: 'text',
  IMAGE: 'image',
  AUDIO: 'audio',
  STICKER: 'sticker',
} as const;

export type MessageType = (typeof MESSAGE_TYPE)[keyof typeof MESSAGE_TYPE];

export const MESSAGE_SOURCE = {
  LIVE: 'live',
  BACKUP: 'backup',
} as const;

export type MessageSource = (typeof MESSAGE_SOURCE)[keyof typeof MESSAGE_SOURCE];

export const BATCH_STATUS = {
  PENDING: 'pending',
  PROCESSING: 'processing',
  DONE: 'done',
  FAILED: 'failed',
} as const;

export type BatchStatus = (typeof BATCH_STATUS)[keyof typeof BATCH_STATUS];

export const TRADE_TYPE = {
  BUY: 'buy',
  SELL: 'sell',
} as const;

export type TradeType = (typeof TRADE_TYPE)[keyof typeof TRADE_TYPE];

export const QUEUE_NAMES = {
  LLM_PROCESS: 'llm:process',
} as const;

/** Redis list key for LLM jobs (cross-language: Node LPUSH, Python BLPOP) */
export const REDIS_LLM_QUEUE_KEY = 'arbitool:llm:jobs';

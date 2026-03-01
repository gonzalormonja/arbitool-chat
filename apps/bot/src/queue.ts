import { Redis } from 'ioredis';
import { config } from './config.js';
import { REDIS_LLM_QUEUE_KEY } from '@arbitool/shared';
import type { LlmProcessJobPayload } from '@arbitool/shared';

const redis = new Redis({ host: config.redis.host, port: config.redis.port });

export async function enqueueLlmProcess(
  payload: LlmProcessJobPayload
): Promise<void> {
  await redis.lpush(REDIS_LLM_QUEUE_KEY, JSON.stringify(payload));
}

export async function closeQueue(): Promise<void> {
  await redis.quit();
}

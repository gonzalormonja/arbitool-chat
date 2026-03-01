function env(name: string, defaultValue?: string): string {
  const v = process.env[name] ?? defaultValue;
  if (v === undefined) throw new Error(`Missing env: ${name}`);
  return v;
}

export const config = {
  database: {
    connectionString:
      process.env.DATABASE_URL ??
      `postgres://${env('PGUSER', 'arbitool')}:${env('PGPASSWORD', 'arbitool')}@${env('PGHOST', 'localhost')}:${env('PGPORT', '5432')}/${env('PGDATABASE', 'arbitool_chat')}`,
  },
  redis: {
    host: process.env.REDIS_HOST ?? 'localhost',
    port: parseInt(process.env.REDIS_PORT ?? '6379', 10),
  },
  mediaPath: process.env.MEDIA_PATH ?? './media',
  enqueueLlmAfterMessages: parseInt(process.env.ENQUEUE_LLM_AFTER_MESSAGES ?? '10', 10),
} as const;

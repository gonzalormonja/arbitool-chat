const env = process.env;

function get(name: string, defaultValue?: string): string {
  const v = env[name] ?? defaultValue;
  if (v === undefined) throw new Error(`Missing env: ${name}`);
  return v;
}

export const config = {
  database: {
    connectionString:
      env.DATABASE_URL ??
      `postgres://${get('PGUSER', 'arbitool')}:${get('PGPASSWORD', 'arbitool')}@${get('PGHOST', 'localhost')}:${get('PGPORT', '5432')}/${get('PGDATABASE', 'arbitool_chat')}`,
  },
  redis: {
    host: env.REDIS_HOST ?? 'localhost',
    port: parseInt(env.REDIS_PORT ?? '6379', 10),
  },
  mediaPath: env.MEDIA_PATH ?? './media',
  batchSize: parseInt(env.BACKUP_BATCH_SIZE ?? '500', 10),
} as const;

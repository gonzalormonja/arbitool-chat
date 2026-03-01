import { createClient } from './client.js';
import { closeDb } from './db.js';
import { closeQueue } from './queue.js';

const client = createClient();

async function shutdown(): Promise<void> {
  try {
    await client.destroy();
    await closeQueue();
    await closeDb();
  } catch (e) {
    console.error('Shutdown error:', e);
  }
  process.exit(0);
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

client.initialize().catch((err) => {
  console.error('Failed to initialize WhatsApp client:', err);
  process.exit(1);
});

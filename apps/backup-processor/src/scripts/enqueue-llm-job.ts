/**
 * Enqueue an LLM job for a group and date range.
 * Usage: node dist/scripts/enqueue-llm-job.js <from_date> <to_date> [group_id]
 * Example: node dist/scripts/enqueue-llm-job.js 2026-01-01 2026-01-10
 */
import { enqueueLlmProcess, closeQueue } from '../queue.js';

function toISOStart(dateStr: string): string {
  return new Date(dateStr + 'T00:00:00.000Z').toISOString();
}

function toISOEnd(dateStr: string): string {
  return new Date(dateStr + 'T23:59:59.999Z').toISOString();
}

async function main() {
  const fromArg = process.argv[2];
  const toArg = process.argv[3];
  const groupIdArg = process.argv[4];

  if (!fromArg || !toArg) {
    console.error('Uso: node dist/scripts/enqueue-llm-job.js <from_date> <to_date> [group_id]');
    console.error('Ejemplo: node dist/scripts/enqueue-llm-job.js 2026-01-01 2026-01-10');
    process.exit(1);
  }

  const group_id = groupIdArg ? parseInt(groupIdArg, 10) : 1;
  const from_date = toISOStart(fromArg);
  const to_date = toISOEnd(toArg);

  const payload = { group_id, from_date, to_date };
  await enqueueLlmProcess(payload);
  await closeQueue();
  console.log('Job encolado:', payload);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

import * as fs from 'node:fs';
import * as path from 'node:path';
import yargs from 'yargs';
import { hideBin } from 'yargs/helpers';
import { config } from './config.js';
import { parseTxtStream } from './parser/txt.js';
import { parseZip } from './parser/zip.js';
import { persistBackup } from './storage.js';
import { closeDb } from './storage.js';
import { closeQueue } from './queue.js';

async function runTxt(
  filePath: string,
  groupName: string,
  groupId: string,
  skipLlm: boolean
) {
  const entries: Awaited<ReturnType<typeof parseZip>>['entries'] = [];
  const stream = fs.createReadStream(filePath, { encoding: 'utf8' });
  for await (const line of parseTxtStream(stream)) {
    entries.push(line);
  }
  console.log(`Parsed ${entries.length} lines from ${filePath}`);
  const { groupId: gid, messageIds } = await persistBackup(
    groupId,
    groupName,
    entries,
    { skipLlm }
  );
  console.log(
    `Group id=${gid}, inserted ${messageIds.length} messages${skipLlm ? ' (LLM job skipped).' : ', LLM job enqueued.'}`
  );
}

async function runZip(
  filePath: string,
  groupName: string,
  groupId: string,
  skipLlm: boolean
) {
  const mediaDir = path.resolve(config.mediaPath);
  const { entries } = await parseZip(filePath, mediaDir);
  console.log(`Parsed ${entries.length} entries from ZIP ${filePath}`);
  const { groupId: gid, messageIds } = await persistBackup(
    groupId,
    groupName,
    entries,
    { skipLlm }
  );
  console.log(
    `Group id=${gid}, inserted ${messageIds.length} messages${skipLlm ? ' (LLM job skipped).' : ', LLM job enqueued.'}`
  );
}

async function main() {
  const argv = await yargs(hideBin(process.argv))
    .option('file', {
      type: 'string',
      demandOption: true,
      description: 'Path to .txt or .zip WhatsApp export',
    })
    .option('group-name', {
      type: 'string',
      demandOption: true,
      description: 'Display name for the group (e.g. chat title)',
    })
    .option('group-id', {
      type: 'string',
      description:
        'External id for the group (default: backup-<slug from group-name)',
    })
    .option('self-name', {
      type: 'string',
      description: 'Name to use for "You" in the export',
    })
    .option('no-llm', {
      type: 'boolean',
      default: false,
      description: 'Only insert messages; do not enqueue LLM job',
    }).argv;

  const filePath = path.resolve(argv.file);
  if (!fs.existsSync(filePath)) {
    console.error('File not found:', filePath);
    process.exit(1);
  }

  const groupName = argv['group-name'];
  const groupId =
    argv['group-id'] ??
    `backup-${groupName.replace(/\s+/g, '-').replace(/[^a-zA-Z0-9-]/g, '').toLowerCase()}`;
  const skipLlm = argv['no-llm'];

  try {
    if (filePath.toLowerCase().endsWith('.zip')) {
      await runZip(filePath, groupName, groupId, skipLlm);
    } else {
      await runTxt(filePath, groupName, groupId, skipLlm);
    }
  } finally {
    await closeQueue();
    await closeDb();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

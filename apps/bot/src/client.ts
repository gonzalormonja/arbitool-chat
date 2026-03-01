import pkg from 'whatsapp-web.js';
const { Client, LocalAuth } = pkg;
import qrcode from 'qrcode-terminal';
import { handleMessage } from './handlers/message.js';

export function createClient(): InstanceType<typeof Client> {
  const client = new Client({
    authStrategy: new LocalAuth({ dataPath: '.wwebjs_auth' }),
    puppeteer: {
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
    },
  });

  client.on('qr', (qr) => {
    qrcode.generate(qr, { small: true });
  });

  client.on('ready', () => {
    console.log('WhatsApp client ready');
  });

  client.on('message', async (msg) => {
    try {
      await handleMessage(msg);
    } catch (err) {
      console.error('Error handling message:', err);
    }
  });

  return client;
}

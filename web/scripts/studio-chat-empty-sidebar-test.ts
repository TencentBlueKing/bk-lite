import fs from 'node:fs';
import path from 'node:path';

const pagePath = path.join(
  process.cwd(),
  'src/app/opspilot/(pages)/studio/chat/page.tsx'
);
const source = fs.readFileSync(pagePath, 'utf8');

if (source.includes('type={currentAgent.icon}')) {
  throw new Error('Collapsed studio chat sidebar must not read currentAgent.icon without a null guard.');
}

console.log('studio-chat-empty-sidebar-test passed');

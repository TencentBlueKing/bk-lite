import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(fileURLToPath(new URL('.', import.meta.url)), '..');
const chatSource = readFileSync(
  join(root, 'src/app/opspilot/components/custom-chat-sse/index.tsx'),
  'utf8'
);

assert.doesNotMatch(
  chatSource,
  /behavior:\s*'smooth'/,
  'streaming chat auto-scroll should not use repeated smooth animations'
);

assert.doesNotMatch(
  chatSource,
  /setTimeout\(\(\)\s*=>\s*scrollToBottom\(\),\s*50\)/,
  'streaming chat updates should not schedule an extra delayed scroll per message update'
);

assert.match(
  chatSource,
  /scrollAnimationFrameRef/,
  'streaming chat auto-scroll should coalesce scroll requests with requestAnimationFrame'
);

assert.match(
  chatSource,
  /cancelAnimationFrame/,
  'streaming chat auto-scroll should cancel stale scheduled frames'
);

console.log('opspilot chat scroll validation passed');

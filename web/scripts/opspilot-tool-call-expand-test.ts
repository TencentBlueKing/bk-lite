import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(fileURLToPath(new URL('.', import.meta.url)), '..');
const chatSource = readFileSync(
  join(root, 'src/app/opspilot/components/custom-chat-sse/index.tsx'),
  'utf8'
);
const rendererSource = readFileSync(
  join(root, 'src/app/opspilot/components/custom-chat-sse/toolCallRenderer.tsx'),
  'utf8'
);

assert.match(
  rendererSource,
  /data-has-detail="\$\{hasDetail\}"/,
  'tool call renderer should mark whether an item has expandable detail'
);

assert.match(
  chatSource,
  /ALLOWED_ATTR:\s*\[[^\]]*'data-has-detail'/s,
  'custom chat sanitizer must preserve data-has-detail so tool item clicks can expand details'
);

assert.match(
  chatSource,
  /getAttribute\('data-has-detail'\)\s*===\s*'true'/,
  'tool item click handler should rely on the preserved detail marker'
);

console.log('opspilot tool call expand validation passed');

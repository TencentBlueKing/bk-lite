import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync(
  new URL('../src/app/opspilot/components/custom-chat-sse/index.tsx', import.meta.url),
  'utf8',
);
const structuredBranch = source.match(
  /if \(hasStructuredReports\) \{([\s\S]*?)\n\s*\/\/ Check if content has inline markers/,
)?.[1] ?? '';

assert.match(structuredBranch, /userChoiceRequests/);
assert.match(structuredBranch, /<UserChoiceCard/);

console.log('structured report 分支会保留用户选择卡片');

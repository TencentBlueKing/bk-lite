import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(fileURLToPath(new URL('.', import.meta.url)), '..');
const source = readFileSync(
  join(root, 'src/app/opspilot/(pages)/tool/page.tsx'),
  'utf8'
);

assert.match(
  source,
  /useState<'builtin' \| 'mcp' \| 'skills'>\('builtin'\)/,
  'tool page should default to the built-in tools tab'
);

assert.match(
  source,
  /options=\{\[\s*\{ label: '工具', value: 'builtin' \},\s*\{ label: '技能', value: 'skills' \},\s*\{ label: 'MCP', value: 'mcp' \},\s*\]\}/s,
  'tool page tabs should be ordered as 工具 / 技能 / MCP'
);

assert.doesNotMatch(
  source,
  /\{ label: '内置', value: 'builtin' \}/,
  'built-in tools tab should be labeled 工具 instead of 内置'
);

console.log('opspilot tool tabs validation passed');

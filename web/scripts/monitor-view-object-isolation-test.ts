import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync(
  new URL('../src/app/monitor/(pages)/view/page.tsx', import.meta.url),
  'utf8'
);

assert.match(
  source,
  /<ViewList\s+key=\{objectId\}/,
  '切换监控对象时必须重建 ViewList，避免搜索结果和表格内部状态泄漏到新对象'
);

console.log('monitor view object isolation tests passed');

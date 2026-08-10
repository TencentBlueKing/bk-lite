import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync(
  new URL('../src/app/opspilot/components/custom-chat-sse/index.tsx', import.meta.url),
  'utf8',
);
assert.doesNotMatch(
  source,
  /hasStructuredReports/,
  '结构化报告不应再切换到整段替换分支',
);
assert.match(source, /CONFIG_ANALYSIS\|USER_CHOICE/);
assert.doesNotMatch(source, /REPORT_PENDING/);
assert.match(source, /marker\.type === 'USER_CHOICE'/);
assert.match(source, /<UserChoiceCard/);

console.log('结构化报告追加展示，并保留用户选择卡片');

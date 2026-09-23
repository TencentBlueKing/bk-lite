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
assert.doesNotMatch(
  source,
  /if \(!content\) return null/,
  '正文为空时仍应渲染 userChoice 卡片，不能直接 return null',
);
assert.match(
  source,
  /t\('chat\.replyToPendingChoice',\s*'回复上面的问题\.\.\.'\)/,
);

const zh = JSON.parse(
  readFileSync(new URL('../src/app/opspilot/locales/zh.json', import.meta.url), 'utf8'),
);
assert.equal(zh.chat.replyToPendingChoice, '回复上面的问题...');

console.log('结构化报告追加展示，并保留用户选择卡片');

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { isUserChoiceRequestClosed, normalizeUserChoiceOptions } from '../src/app/opspilot/components/custom-chat-sse/userChoiceOptions';

const source = readFileSync(
  new URL('../src/app/opspilot/components/custom-chat-sse/UserChoiceCard.tsx', import.meta.url),
  'utf8',
);

assert.match(source, /normalizeUserChoiceOptions\(request\.options\)/);
assert.match(source, /getPopupContainer=\{\(\) => document\.body\}/);
assert.match(source, /zIndex: 11000/);
assert.match(source, /choiceOptions\.map/);
assert.doesNotMatch(
  source,
  /options=\{request\.options\.map/,
  '下拉选项必须走规范化后的 choiceOptions，不能直接用 request.options',
);

{
  const options = normalizeUserChoiceOptions([
    'Host',
    { key: 'ECS', label: '云服务器 ECS' },
    { value: 'Aliyun', display_name: '阿里云' },
    'Host',
    { key: '', label: 'empty' },
    12,
    null,
  ]);
  assert.deepEqual(
    options.map((item) => ({ key: item.key, label: item.label })),
    [
      { key: 'Host', label: 'Host' },
      { key: 'ECS', label: '云服务器 ECS' },
      { key: 'Aliyun', label: '阿里云' },
    ],
  );
}

{
  const options = normalizeUserChoiceOptions([
    'CNwareVM',
    'Aliyun',
    'ECS',
    'CDN',
    'WAF',
    'OSS',
    'RDSMySQL',
    'RDSPG',
    'AliyunRedis',
    'AliyunMongoDB',
    'AliyunKafka',
    'EIP',
    'Sybase',
    'PolarDB_PG',
  ]);
  assert.equal(options.length, 14);
  assert.ok(options.every((item) => item.key && item.label));
}

assert.equal(isUserChoiceRequestClosed('pending'), false);
assert.equal(isUserChoiceRequestClosed('submitted'), true);
assert.equal(isUserChoiceRequestClosed('timeout'), true);
assert.doesNotMatch(
  source,
  /isTimedOut/,
  '前端倒计时到 0 不得把待选卡片当成 completed 卸掉',
);

console.log('用户选择卡片下拉：弹层挂到 body，并兼容字符串选项');

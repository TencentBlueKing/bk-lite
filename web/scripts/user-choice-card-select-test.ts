import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { applyAnsweredUserChoices, choiceRequestFromVisibleText, isUserChoiceRequestClosed, normalizeUserChoiceOptions, stripChoicePromptFromContent } from '../src/app/opspilot/components/custom-chat-sse/userChoiceOptions';

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

assert.doesNotMatch(source, /postUserChoice/);
assert.match(source, /onSendMessage\?\.\(labels\.join/);
assert.doesNotMatch(source, /if \(isCompleted\) \{\s*return null/);

{
  const request = {
    choice_id: 'c1',
    title: '选一个',
    options: [{ key: 'host', label: '主机' }, { key: 'pod', label: 'Pod' }],
    status: 'pending' as const,
    selected: [],
  };
  const clicked = applyAnsweredUserChoices([
    { role: 'bot', content: '', userChoiceRequests: [request] },
    { role: 'user', content: '主机' },
  ]);
  assert.equal(clicked[0].userChoiceRequests?.[0].status, 'submitted');
  assert.deepEqual(clicked[0].userChoiceRequests?.[0].selected, ['host']);

  const typed = applyAnsweredUserChoices([
    { role: 'bot', content: '', userChoiceRequests: [{ ...request, choice_id: 'c2' }] },
    { role: 'user', content: '我想自己说' },
  ]);
  assert.equal(typed[0].userChoiceRequests?.[0].status, 'submitted');
  assert.deepEqual(typed[0].userChoiceRequests?.[0].selected, []);

  const open = applyAnsweredUserChoices([
    { role: 'bot', content: '', userChoiceRequests: [{ ...request, choice_id: 'c3' }] },
  ]);
assert.equal(open[0].userChoiceRequests?.[0].status, 'pending');
}

{
  const stripped = stripChoicePromptFromContent(
    'web-01 是哪种类型？\n\n1. JVM\n2. Kafka\n3. Oracle',
    [{
      choice_id: 'c',
      title: 'web-01 是哪种类型？',
      options: [
        { key: 'JVM', label: 'JVM' },
        { key: 'Kafka', label: 'Kafka' },
        { key: 'Oracle', label: 'Oracle' },
      ],
      status: 'pending',
      selected: [],
    }],
  );
  assert.equal(stripped, '');
}

assert.equal(choiceRequestFromVisibleText('这通常意味着：\n\n1. 采集未上报\n2. 仅完成纳管'), null);
assert.ok(choiceRequestFromVisibleText('web-01 属于哪种类型？\n\n1. 主机\n2. Pod'));
assert.equal(isUserChoiceRequestClosed('pending'), false);
assert.equal(isUserChoiceRequestClosed('submitted'), true);
assert.equal(isUserChoiceRequestClosed('timeout'), true);
assert.doesNotMatch(
  source,
  /isTimedOut/,
  '前端倒计时到 0 不得把待选卡片当成 completed 卸掉',
);

console.log('用户选择卡片下拉：弹层挂到 body，并兼容字符串选项');

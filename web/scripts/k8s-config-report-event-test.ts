import assert from 'node:assert/strict';

import { AGUIMessageHandler } from '../src/app/opspilot/components/custom-chat-sse/aguiMessageHandler';

const botMessage = {
  id: 'bot-1',
  role: 'bot',
  content: '',
  updateAt: new Date().toISOString(),
} as any;

let messages = [botMessage];

const updateMessages = (updater: (prev: any[]) => any[]) => {
  messages = updater(messages);
};

const handler = new AGUIMessageHandler(botMessage, updateMessages, new Map());

handler.handle({ type: 'RUN_STARTED' } as any);
handler.handle({
  type: 'CUSTOM',
  name: 'config_analysis_report',
  value: {
    report_id: 'report-1',
    markdown: '# 配置检查报告 - Kubernetes - 1\n\n## High\n- 未配置存活探针',
  },
} as any);
handler.handle({
  type: 'CUSTOM',
  name: 'user_choice_request',
  value: {
    execution_id: 'exec-1',
    node_id: 'node-1',
    choice_id: 'choice-1',
    title: '请选择修复展示方式',
    description: '',
    options: [
      { key: 'category', label: '按问题类别聚合' },
      { key: 'target', label: '按工作负载聚合' },
      { key: 'all', label: '全部一次性展示' },
    ],
    multiple: false,
    min_select: 1,
    max_select: 1,
    timeout_seconds: 120,
    default_keys: ['category'],
    display_hint: 'auto',
  },
} as any);

const finalContent = messages[0]?.content || '';

assert.equal(finalContent.includes('配置检查报告 - Kubernetes - 1'), true);
assert.equal(finalContent.match(/配置检查报告 - Kubernetes - 1/g)?.length || 0, 1);
assert.equal(finalContent.includes('<!--USER_CHOICE:choice-1-->'), true);

console.log('k8s config report event test passed');

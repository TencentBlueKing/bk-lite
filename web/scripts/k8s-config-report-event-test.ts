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
    title: '配置检查报告',
    cluster_name: 'Kubernetes - 1',
    summary: {
      total: 36,
      problematic: 32,
      healthy: 4,
      top_recommendation: '优先补齐高危问题对应的探针与资源限制配置',
    },
    severity_sections: [
      {
        severity: 'high',
        title: 'High',
        items: [
          {
            issue: '未配置存活探针',
            count: 10,
            workloads: ['gateway (opspilot-check-a)'],
            risk: '容器异常时无法被及时发现并自愈',
          },
        ],
      },
    ],
    recommendations: [
      {
        priority: 'P1',
        action: '补齐 liveness / readiness probe',
        target: 'gateway',
        benefit: '提高发布稳定性与故障自愈能力',
      },
    ],
    markdown: '# 配置检查报告 - Kubernetes - 1',
    fallback_markdown: '# 配置检查报告 - Kubernetes - 1',
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

assert.equal(messages[0]?.configAnalysisReports?.length, 1);
assert.equal(finalContent.includes('<!--CONFIG_ANALYSIS:report-1-->'), true);
assert.equal(finalContent.match(/<!--CONFIG_ANALYSIS:report-1-->/g)?.length || 0, 1);
assert.equal(finalContent.includes('<!--USER_CHOICE:choice-1-->'), true);

const fallbackMessage = {
  id: 'bot-2',
  role: 'bot',
  content: '',
  updateAt: new Date().toISOString(),
} as any;

let fallbackMessages = [fallbackMessage];
const fallbackHandler = new AGUIMessageHandler(fallbackMessage, updater => {
  fallbackMessages = updater(fallbackMessages);
}, new Map());

fallbackHandler.handle({ type: 'RUN_STARTED' } as any);
fallbackHandler.handle({
  type: 'CUSTOM',
  name: 'config_analysis_report',
  value: {
    report_id: 'fallback-1',
    markdown: '# 仅 markdown',
  },
} as any);

assert.equal(fallbackMessages[0]?.content.includes('# 仅 markdown'), true);
assert.equal(fallbackMessages[0]?.configAnalysisReports?.length || 0, 0);

console.log('k8s config report event test passed');

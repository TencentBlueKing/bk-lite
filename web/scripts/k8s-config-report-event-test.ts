import assert from 'node:assert/strict';

import { AGUIMessageHandler } from '../src/app/opspilot/components/custom-chat-sse/aguiMessageHandler';
import { AGUIMessage, ConfigAnalysisReportValue } from '../src/app/opspilot/types/chat';
import { CustomChatMessage } from '../src/app/opspilot/types/global';

const botMessage: CustomChatMessage = {
  id: 'bot-1',
  role: 'bot',
  content: '',
  updateAt: new Date().toISOString(),
};

let messages = [botMessage];

const updateMessages = (updater: (prev: CustomChatMessage[]) => CustomChatMessage[]) => {
  messages = updater(messages);
};

const handler = new AGUIMessageHandler(botMessage, updateMessages, new Map());

const structuredPayload = {
  report_id: 'report-1',
  title: '配置检查报告 - Kubernetes - 1',
  cluster_name: 'Kubernetes - 1',
  scope: {
    cluster_name: 'Kubernetes - 1',
    namespace: 'payments',
    instance_name: 'prod-cluster',
    name: 'gateway',
    target_name: 'gateway',
  },
  scan_range: {
    offset: 50,
    limit: 25,
    has_more: true,
  },
  summary: {
    total: 36,
    problematic: 32,
    healthy: 4,
  },
  severity_sections: [
    {
      severity: 'critical',
      title: 'Critical',
      issues: [
        {
          issue: '容器以 root 运行',
          count: 1,
          workloads: ['gateway (payments)'],
          risk: '容器逃逸后攻击者可能获得宿主机 root 权限',
        },
      ],
    },
    {
      severity: 'high',
      title: 'High',
      issues: [
        {
          issue: '未配置存活探针',
          count: 10,
          workloads: ['gateway (payments)'],
          risk: '容器异常时无法被及时发现并自愈',
        },
      ],
    },
  ],
  recommendations: [
    {
      priority: 'P0',
      action: '配置 securityContext.runAsNonRoot: true',
      target: 'gateway (payments)',
      benefit: '降低高权限容器风险',
    },
    {
      priority: 'P1',
      action: '补齐 liveness / readiness probe',
      target: 'gateway (payments)',
      benefit: '提高发布稳定性与故障自愈能力',
    },
  ],
  markdown: '# 配置检查报告 - Kubernetes - 1',
  fallback_markdown: '# 配置检查报告 - Kubernetes - 1',
} satisfies ConfigAnalysisReportValue;

handler.handle({
  type: 'RUN_STARTED',
  timestamp: Date.now(),
} satisfies AGUIMessage);
handler.handle({
  type: 'CUSTOM',
  timestamp: Date.now(),
  name: 'config_analysis_report',
  value: structuredPayload,
} satisfies AGUIMessage);
handler.handle({
  type: 'CUSTOM',
  timestamp: Date.now(),
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
} satisfies AGUIMessage);

const finalContent = messages[0]?.content || '';

assert.equal(messages[0]?.configAnalysisReports?.length, 1);
assert.deepEqual(messages[0]?.configAnalysisReports?.[0]?.scope, structuredPayload.scope);
assert.deepEqual(messages[0]?.configAnalysisReports?.[0]?.scan_range, structuredPayload.scan_range);
assert.equal(messages[0]?.configAnalysisReports?.[0]?.severity_sections?.[0]?.issues?.[0]?.issue, '容器以 root 运行');
assert.equal(messages[0]?.configAnalysisReports?.[0]?.recommendations?.[0]?.priority, 'P0');
assert.equal(finalContent.includes('<!--CONFIG_ANALYSIS:report-1-->'), true);
assert.equal(finalContent.match(/<!--CONFIG_ANALYSIS:report-1-->/g)?.length || 0, 1);
assert.equal(finalContent.includes('<!--USER_CHOICE:choice-1-->'), true);

const fallbackMessage: CustomChatMessage = {
  id: 'bot-2',
  role: 'bot',
  content: '',
  updateAt: new Date().toISOString(),
};

let fallbackMessages = [fallbackMessage];
const fallbackHandler = new AGUIMessageHandler(fallbackMessage, updater => {
  fallbackMessages = updater(fallbackMessages);
}, new Map());

fallbackHandler.handle({
  type: 'RUN_STARTED',
  timestamp: Date.now(),
} satisfies AGUIMessage);
fallbackHandler.handle({
  type: 'CUSTOM',
  timestamp: Date.now(),
  name: 'config_analysis_report',
  value: {
    title: '缺少 report_id 的结构化载荷',
    cluster_name: 'Kubernetes - 1',
    summary: {
      total: 1,
      problematic: 1,
      healthy: 0,
    },
    severity_sections: [],
    recommendations: [],
    markdown: '# 仅 markdown',
  },
} satisfies AGUIMessage);

assert.equal(fallbackMessages[0]?.content.includes('# 仅 markdown'), true);
assert.equal(fallbackMessages[0]?.configAnalysisReports?.length || 0, 0);
assert.equal(fallbackMessages[0]?.content.includes('<!--CONFIG_ANALYSIS:undefined-->'), false);

console.log('k8s config report event test passed');

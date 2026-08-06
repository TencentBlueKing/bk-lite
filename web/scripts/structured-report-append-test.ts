import assert from 'node:assert/strict';

import { AGUIMessageHandler } from '../src/app/opspilot/components/custom-chat-sse/aguiMessageHandler';
import { AGUIMessage } from '../src/app/opspilot/types/chat';
import { CustomChatMessage } from '../src/app/opspilot/types/global';

let messages: CustomChatMessage[] = [{ id: 'bot-report', role: 'bot', content: '' }];
const handler = new AGUIMessageHandler(
  messages[0],
  updater => {
    messages = updater(messages);
  },
  new Map(),
);
const send = (message: Omit<AGUIMessage, 'timestamp'>) => handler.handle({
  timestamp: Date.now(),
  ...message,
});
const reportId = 'config_analysis_report_exec-1';

// 兼容仍会发送生命周期事件的旧后端：它们不能再隐藏文本或创建替换占位。
send({
  type: 'CUSTOM',
  name: 'report_started',
  value: {
    report_id: reportId,
    capability: 'config_analysis_report',
    status: 'running',
  },
});
send({ type: 'TEXT_MESSAGE_CONTENT', delta: '配置检查已经完成，下面是详细结果。' });
send({
  type: 'CUSTOM',
  name: 'config_analysis_report',
  value: {
    report_id: reportId,
    title: '配置检查报告',
    cluster_name: 'Kubernetes - 1',
    summary: { total: 2, problematic: 1, healthy: 1 },
    severity_sections: [{
      severity: 'high',
      title: '高风险',
      issues: [{ issue: '未配置探针', count: 1, workloads: ['api'], risk: '服务不可用' }],
    }],
    recommendations: [{ priority: 'P0', action: '补充探针', target: 'api', benefit: '提高可用性' }],
    markdown: '# 配置检查报告',
  },
});

const content = messages[0].content;
const textIndex = content.indexOf('配置检查已经完成');
const cardIndex = content.indexOf(`CONFIG_ANALYSIS:${reportId}`);

assert.ok(textIndex >= 0, '结构化报告不能吞掉已经输出的文本');
assert.ok(cardIndex > textIndex, '完成的结构化卡片应追加在文本后面');
assert.doesNotMatch(content, /REPORT_PENDING/, '不再展示会替换内容的加载占位');

console.log('structured report append test passed');

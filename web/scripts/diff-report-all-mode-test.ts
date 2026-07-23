import assert from 'node:assert/strict';

import { getDiffReportItemPresentation } from '../src/app/opspilot/components/custom-chat-sse/diffReportItemPresentation';

const allMode = getDiffReportItemPresentation({
  workload_name: '全部（59 个目标）',
  workload_type: 'All',
  namespace: '-',
  severity: 'critical',
});

assert.deepEqual(allMode, {
  badgeLabel: '全部',
  badgeTone: 'processing',
  targetLabel: '全部（59 个目标）',
  riskLabel: '最高风险：严重',
});

const targetMode = getDiffReportItemPresentation({
  workload_name: 'api',
  workload_type: 'Deployment',
  namespace: 'default',
  severity: 'high',
});

assert.deepEqual(targetMode, {
  badgeLabel: '高危',
  badgeTone: 'volcano',
  targetLabel: 'default/api',
  riskLabel: '',
});

console.log('diff report all mode tests passed');

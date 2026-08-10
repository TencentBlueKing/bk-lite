import assert from 'node:assert/strict';

import { getConfigAnalysisSummaryText } from '../src/app/opspilot/components/custom-chat-sse/configAnalysisReportSummary';

assert.equal(
  getConfigAnalysisSummaryText({
    problematicCount: 74,
    hasIssueDetails: true,
  }),
  '已按风险等级汇总 74 个存在问题的工作负载，请查看下方问题明细。',
);

assert.equal(
  getConfigAnalysisSummaryText({
    problematicCount: 74,
    hasIssueDetails: false,
  }),
  '当前报告返回了问题统计，但结构化明细暂未返回，请结合原始扫描结果继续排查。',
);

assert.equal(
  getConfigAnalysisSummaryText({
    problematicCount: 0,
    hasIssueDetails: false,
  }),
  '当前扫描结果未发现明显风险，暂无额外修复建议。',
);

console.log('config analysis report summary tests passed');

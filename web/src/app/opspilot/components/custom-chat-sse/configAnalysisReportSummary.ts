interface ConfigAnalysisSummaryInput {
  problematicCount: number;
  hasIssueDetails: boolean;
  topRecommendation?: string;
}

export const getConfigAnalysisSummaryText = ({
  problematicCount,
  hasIssueDetails,
  topRecommendation,
}: ConfigAnalysisSummaryInput): string => {
  if (topRecommendation?.trim()) return topRecommendation.trim();
  if (problematicCount <= 0) {
    return '当前扫描结果未发现明显风险，暂无额外修复建议。';
  }
  if (!hasIssueDetails) {
    return '当前报告返回了问题统计，但结构化明细暂未返回，请结合原始扫描结果继续排查。';
  }
  return `已按风险等级汇总 ${problematicCount} 个存在问题的工作负载，请查看下方问题明细。`;
};

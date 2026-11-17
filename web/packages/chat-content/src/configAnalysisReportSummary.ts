interface ConfigAnalysisSummaryInput {
  problematicCount: number;
  hasIssueDetails: boolean;
  topRecommendation?: string;
}

type Translate = (
  key: string,
  defaultMessage?: string,
  values?: Record<string, string | number>,
) => string;

export const getConfigAnalysisSummaryText = (
  {
    problematicCount,
    hasIssueDetails,
    topRecommendation,
  }: ConfigAnalysisSummaryInput,
  t: Translate
): string => {
  // 报告自带建议时原样展示（服务端内容，不翻译）
  if (topRecommendation?.trim()) return topRecommendation.trim();
  if (problematicCount <= 0) {
    return t('chat.configAnalysis.noRisk', '当前扫描结果未发现明显风险，暂无额外修复建议。');
  }
  if (!hasIssueDetails) {
    return t(
      'chat.configAnalysis.noDetails',
      '当前报告返回了问题统计，但结构化明细暂未返回，请结合原始扫描结果继续排查。'
    );
  }
  return t(
    'chat.configAnalysis.summary',
    '已按风险等级汇总 {count} 个存在问题的工作负载，请查看下方问题明细。',
    { count: problematicCount }
  );
};

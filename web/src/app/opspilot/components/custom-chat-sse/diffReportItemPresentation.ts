type Severity = 'critical' | 'high' | 'medium' | 'low' | 'warning' | 'info';

const severityPresentation: Record<Severity, { label: string; tone: string }> = {
  critical: { label: '严重', tone: 'error' },
  high: { label: '高危', tone: 'volcano' },
  medium: { label: '中风险', tone: 'warning' },
  low: { label: '低风险', tone: 'success' },
  warning: { label: '警告', tone: 'warning' },
  info: { label: '提示', tone: 'processing' },
};

interface DiffReportItemIdentity {
  workload_name: string;
  workload_type: string;
  namespace: string;
  severity?: string;
}

export const getDiffReportItemPresentation = (item: DiffReportItemIdentity) => {
  const severity = severityPresentation[item.severity as Severity] ?? severityPresentation.info;
  const isAllMode = item.workload_type.trim().toLowerCase() === 'all';

  if (isAllMode) {
    return {
      badgeLabel: '全部',
      badgeTone: 'processing',
      targetLabel: item.workload_name,
      riskLabel: `最高风险：${severity.label}`,
    };
  }

  const namespacePrefix = item.namespace && item.namespace !== '-' ? `${item.namespace}/` : '';
  return {
    badgeLabel: severity.label,
    badgeTone: severity.tone,
    targetLabel: `${namespacePrefix}${item.workload_name}`,
    riskLabel: '',
  };
};

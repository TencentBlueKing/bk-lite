type Severity = 'critical' | 'high' | 'medium' | 'low' | 'warning' | 'info';

type Translate = (
  key: string,
  defaultMessage?: string,
  values?: Record<string, string | number>,
) => string;

/** 严重级别在聊天侧与配置分析侧共用同一套 locale key。 */
export const configSeverityLabelKey: Record<Severity, string> = {
  critical: 'configSeverity.critical',
  high: 'configSeverity.high',
  medium: 'configSeverity.medium',
  low: 'configSeverity.low',
  warning: 'configSeverity.warning',
  info: 'configSeverity.info',
};

const severityPresentation: Record<Severity, { tone: string; labelKey: string }> = {
  critical: { tone: 'error', labelKey: configSeverityLabelKey.critical },
  high: { tone: 'volcano', labelKey: configSeverityLabelKey.high },
  medium: { tone: 'warning', labelKey: configSeverityLabelKey.medium },
  low: { tone: 'success', labelKey: configSeverityLabelKey.low },
  warning: { tone: 'warning', labelKey: configSeverityLabelKey.warning },
  info: { tone: 'processing', labelKey: configSeverityLabelKey.info },
};

interface DiffReportItemIdentity {
  workload_name: string;
  workload_type: string;
  namespace: string;
  severity?: string;
}

export const getDiffReportItemPresentation = (
  item: DiffReportItemIdentity,
  t: Translate,
) => {
  const severity = severityPresentation[item.severity as Severity] ?? severityPresentation.info;
  const severityLabel = t(severity.labelKey, item.severity as string);
  const isAllMode = item.workload_type.trim().toLowerCase() === 'all';

  if (isAllMode) {
    return {
      badgeLabel: t('chat.diffReport.all', '全部'),
      badgeTone: 'processing',
      targetLabel: item.workload_name,
      riskLabel: t('chat.diffReport.topRisk', '最高风险：{level}', { level: severityLabel }),
    };
  }

  const namespacePrefix = item.namespace && item.namespace !== '-' ? `${item.namespace}/` : '';
  return {
    badgeLabel: severityLabel,
    badgeTone: severity.tone,
    targetLabel: `${namespacePrefix}${item.workload_name}`,
    riskLabel: '',
  };
};

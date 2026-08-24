import type {
  BaselineComplianceDistribution,
  BaselineCompliancePerspective,
  BaselineComplianceResultScope,
  BaselineComplianceResultStatus,
  ComplianceStatus,
} from '@/app/patch-manager/types';

export interface ComplianceResultPresentation {
  color: string;
  labelKey: string;
  hostScoped: boolean;
}

const STATUS_COLORS: Record<BaselineComplianceResultStatus, string> = {
  satisfied: 'success',
  missing: 'error',
  not_applicable: 'default',
  unknown: 'warning',
  pending: 'default',
  evaluating: 'processing',
  failed: 'error',
};

const HOST_BORDER_COLORS: Record<ComplianceStatus, string> = {
  compliant: '#52c41a',
  non_compliant: '#ff4d4f',
  pending: '#d9d9d9',
  evaluating: '#1677ff',
  failed: '#faad14',
  unconfigured: '#faad14',
  unknown: '#faad14',
  not_applicable: '#d9d9d9',
};

export function getComplianceObjectBorderColor({
  perspective,
  complianceStatus,
  distribution,
}: {
  perspective: BaselineCompliancePerspective;
  complianceStatus?: ComplianceStatus;
  distribution: BaselineComplianceDistribution[];
}): string {
  if (perspective === 'host') {
    return complianceStatus ? HOST_BORDER_COLORS[complianceStatus] : '#d9d9d9';
  }

  const statuses = new Set(
    distribution.filter(({ count }) => count > 0).map(({ status }) => status),
  );
  if (statuses.has('missing') || statuses.has('failed')) return '#ff4d4f';
  if (statuses.has('unknown')) return '#faad14';
  if (statuses.has('evaluating')) return '#1677ff';
  if (statuses.has('pending')) return '#d9d9d9';
  if (statuses.has('satisfied')) return '#52c41a';
  return '#d9d9d9';
}

export function getComplianceResultPresentation(
  status: BaselineComplianceResultStatus,
  scope: BaselineComplianceResultScope,
): ComplianceResultPresentation {
  return {
    color: STATUS_COLORS[status],
    labelKey: `patchManager.baseline.complianceDetail.status.${status}`,
    hostScoped: scope === 'host',
  };
}

function formatEvidenceValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map(formatEvidenceValue).join('、');
  }
  if (value && typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => `${key.replaceAll('_', ' ')}=${formatEvidenceValue(item)}`)
      .join(', ');
  }
  if (value === null || value === undefined || value === '') return '--';
  return String(value);
}

export function formatComplianceEvidence(
  evidence: Record<string, unknown> | null | undefined,
): string {
  if (!evidence || Object.keys(evidence).length === 0) return '--';
  return Object.entries(evidence)
    .map(([key, value]) => `${key.replaceAll('_', ' ')}: ${formatEvidenceValue(value)}`)
    .join('\n');
}

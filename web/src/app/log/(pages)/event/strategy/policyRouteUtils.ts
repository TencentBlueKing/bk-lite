export type LogPolicyType = 'keyword' | 'aggregate';

const POLICY_TYPES = new Set<LogPolicyType>(['keyword', 'aggregate']);

export const getCreatePolicyType = (
  alertType?: string | null
): LogPolicyType | null => {
  if (POLICY_TYPES.has(alertType as LogPolicyType)) {
    return alertType as LogPolicyType;
  }
  return null;
};

export const buildStrategyDetailUrl = (
  type: string,
  row: {
    id?: string | number;
    name?: string;
    alertType?: string | null;
  } = {}
) => {
  const params = new URLSearchParams({ type });
  if (row.id !== undefined && row.id !== '') {
    params.set('id', String(row.id));
  }
  if (row.name) {
    params.set('name', row.name);
  }
  const alertType = getCreatePolicyType(row.alertType);
  if (alertType) {
    params.set('alert_type', alertType);
  }
  return `/log/event/strategy/detail?${params.toString()}`;
};

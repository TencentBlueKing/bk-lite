export function buildAlarmDetailTemplateHint(origin: string): string {
  const base = origin.replace(/\/$/, '');
  return `${base}/alarm/alarms?alert_id={{ alert.alert_id }}`;
}

export function buildAlarmDetailUrl(origin: string, alertId: string): string {
  const base = origin.replace(/\/$/, '');
  const query = new URLSearchParams({ alert_id: alertId });
  return `${base}/alarm/alarms?${query.toString()}`;
}

export function applyAlarmLocateParams<T extends Record<string, unknown>>(
  params: T,
  alertId: string,
): T {
  return {
    ...params,
    status: '',
    created_at_after: '',
    created_at_before: '',
    activate: '',
    my_alert: '',
    alert_id: alertId,
  };
}

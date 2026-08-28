import dayjs from 'dayjs';
import type { ApmEnvironmentView, ApmEvent, ApmService, ApmServiceRed, ApmSlo, CatalogStatus } from '@/app/apm/types';

export type TimeWindow = '15m' | '1h' | '4h' | '1d' | '7d';
export type AlertStatusFilter = 'critical' | 'error' | 'warning' | 'info' | 'normal';
export type ActiveAlertStatus = AlertStatusFilter;

export interface ServiceEnvironmentRow extends ApmEnvironmentView {
  key: string;
  serviceId: string;
  applicationName: string;
  namespace: string;
  serviceName: string;
  language: string;
  serviceOrganizationIds: number[];
  serviceArchivedAt: string | null;
  archiveReason: string;
}

export const TIME_WINDOWS: TimeWindow[] = ['15m', '1h', '4h', '1d', '7d'];

export const timeWindowUnits: Record<TimeWindow, [number, dayjs.ManipulateType]> = {
  '15m': [15, 'minute'],
  '1h': [1, 'hour'],
  '4h': [4, 'hour'],
  '1d': [1, 'day'],
  '7d': [7, 'day'],
};

export const isTimeWindow = (value: string | null): value is TimeWindow => (
  value !== null && (TIME_WINDOWS as string[]).includes(value)
);

export const isAlertStatusFilter = (value: string | null): value is AlertStatusFilter => (
  value === 'critical' || value === 'error' || value === 'warning' || value === 'info' || value === 'normal'
);

export const metricKey = (serviceId: string, environment: string) => `${serviceId}:${environment}`;
export const alertKey = (serviceName: string, environment: string) => `${serviceName}::${environment}`;

const severityRank: Record<string, number> = {
  critical: 1,
  error: 2,
  warning: 3,
  info: 4,
};

export const alertStatusFromLevel = (level?: number): ActiveAlertStatus => {
  if (level === 1) return 'critical';
  if (level === 2) return 'error';
  if (level === 3) return 'warning';
  if (level === 4) return 'info';
  return 'normal';
};

export const alertStatusMeta: Record<ActiveAlertStatus, { id: string; fallback: string; color?: string }> = {
  critical: { id: 'apm.severity.critical', fallback: '严重', color: 'red' },
  error: { id: 'apm.severity.error', fallback: '错误', color: 'volcano' },
  warning: { id: 'apm.severity.warning', fallback: '警告', color: 'orange' },
  info: { id: 'apm.severity.info', fallback: '提示', color: 'blue' },
  normal: { id: 'apm.severity.normal', fallback: '正常', color: 'green' },
};

export function expandServiceRows(services: ApmService[]): ServiceEnvironmentRow[] {
  return services.flatMap((service) => {
    const environmentViews = service.environment_views.length
      ? service.environment_views
      : [{ environment: '', last_seen_at: service.last_seen_at, status: service.status }];
    return environmentViews.map((environmentView) => ({
      ...environmentView,
      status: service.archived_at ? 'archived' as const : environmentView.status,
      key: `${service.id}:${environmentView.environment}`,
      serviceId: service.id,
      applicationName: service.application_name,
      namespace: service.namespace,
      serviceName: service.name,
      language: service.language,
      serviceOrganizationIds: service.organization_ids,
      serviceArchivedAt: service.archived_at,
      archiveReason: service.archive_reason,
    }));
  });
}

export function countActiveAlerts(events: ApmEvent[]) {
  const counts = new Map<string, { count: number; level: number }>();
  events.forEach((event) => {
    if (event.status !== 'active') return;
    const key = alertKey(event.service, event.environment || '');
    const current = counts.get(key) ?? { count: 0, level: 5 };
    const level = severityRank[event.severity] ?? 4;
    counts.set(key, {
      count: current.count + 1,
      level: Math.min(current.level, level),
    });
  });
  return counts;
}

export function indexEnabledSlos(slos: ApmSlo[]) {
  const map = new Map<string, ApmSlo>();
  slos.forEach((slo) => {
    if (!slo.is_enabled) return;
    const key = metricKey(slo.service_id, slo.environment);
    const existing = map.get(key);
    if (!existing || (slo.budget_remaining ?? 1) < (existing.budget_remaining ?? 1)) {
      map.set(key, slo);
    }
  });
  return map;
}

export function timeWindowRange(timeWindow: TimeWindow) {
  const [amount, unit] = timeWindowUnits[timeWindow];
  const endedAt = dayjs();
  return { startedAt: endedAt.subtract(amount, unit), endedAt };
}

export type { CatalogStatus, ApmServiceRed };

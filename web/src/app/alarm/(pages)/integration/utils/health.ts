import { SourceItem } from '@/app/alarm/types/integration';

export interface HealthStatus {
  key: 'healthy' | 'warning' | 'stale' | 'silent' | 'stopped' | 'inactive';
  labelKey: string;
  color: string;
  bg: string;
}

const H24 = 86400000;
const H7D = H24 * 7;

export function getHealth(src: SourceItem): HealthStatus {
  if (!src.is_active) {
    return { key: 'stopped', labelKey: 'integration.healthStopped', color: '#f53f3f', bg: '#fff1f0' };
  }
  if (!src.is_effective) {
    return { key: 'inactive', labelKey: 'integration.healthInactive', color: '#86909c', bg: '#f2f3f5' };
  }
  if (!src.last_event_time) {
    return { key: 'silent', labelKey: 'integration.healthNoData', color: '#ff7d00', bg: '#fff7e8' };
  }
  const diff = Date.now() - new Date(src.last_event_time).getTime();
  if (diff < H24) {
    return { key: 'healthy', labelKey: 'integration.healthHealthy', color: '#00b42a', bg: '#e8ffea' };
  }
  if (diff < H7D) {
    return { key: 'warning', labelKey: 'integration.healthSilent', color: '#ff7d00', bg: '#fff7e8' };
  }
  return { key: 'stale', labelKey: 'integration.healthStale', color: '#ff7d00', bg: '#fff7e8' };
}

export function matchesStatusFilter(
  health: HealthStatus,
  statusFilter: string
): boolean {
  if (statusFilter === 'all') return true;
  if (statusFilter === 'healthy') return health.key === 'healthy';
  if (statusFilter === 'warning') return ['warning', 'stale', 'silent'].includes(health.key);
  if (statusFilter === 'inactive') return ['stopped', 'inactive'].includes(health.key);
  return true;
}

const LOGO_COLORS: Record<string, string> = {
  restful: '#5b8def',
  nats: '#27aae1',
  k8s: '#326ce5',
  snmp_trap: '#c10d0c',
  prometheus: '#e6522c',
  zabbix: '#d40000',
};

export function getLogoColor(sourceId: string): string {
  return LOGO_COLORS[sourceId] || '#3370ff';
}

export function formatEventCount(n: number | null | undefined | string): string {
  if (n === null || n === undefined || n === '') return '--';
  const num = typeof n === 'string' ? parseInt(n, 10) : n;
  if (isNaN(num)) return '--';
  if (num >= 10000) return (num / 1000).toFixed(1) + 'k';
  return String(num);
}

export function formatTimestamp(ts: string | null | undefined): string {
  if (!ts) return '--';
  const d = new Date(ts);
  if (isNaN(d.getTime())) return '--';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

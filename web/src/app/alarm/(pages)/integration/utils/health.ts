import { SourceItem } from '@/app/alarm/types/integration';
import {
  STATUS_TEXT,
  HEALTH_BG,
  SOURCE_LOGO,
  SOURCE_LOGO_FALLBACK,
} from '@/app/alarm/constants/colors';

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
    return { key: 'stopped', labelKey: 'integration.healthStopped', color: STATUS_TEXT.TREND_UP_RED, bg: HEALTH_BG.RED_BG };
  }
  if (!src.is_effective) {
    return { key: 'inactive', labelKey: 'integration.healthInactive', color: STATUS_TEXT.NEUTRAL_GRAY, bg: HEALTH_BG.GRAY_BG };
  }
  if (!src.last_event_time) {
    return { key: 'silent', labelKey: 'integration.healthNoData', color: STATUS_TEXT.WARN_ORANGE, bg: HEALTH_BG.ORANGE_BG };
  }
  const diff = Date.now() - new Date(src.last_event_time).getTime();
  if (diff < H24) {
    return { key: 'healthy', labelKey: 'integration.healthHealthy', color: STATUS_TEXT.TREND_DOWN_GREEN, bg: HEALTH_BG.GREEN_BG };
  }
  if (diff < H7D) {
    return { key: 'warning', labelKey: 'integration.healthSilent', color: STATUS_TEXT.WARN_ORANGE, bg: HEALTH_BG.ORANGE_BG };
  }
  return { key: 'stale', labelKey: 'integration.healthStale', color: STATUS_TEXT.WARN_ORANGE, bg: HEALTH_BG.ORANGE_BG };
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

export function getLogoColor(sourceId: string): string {
  return SOURCE_LOGO[sourceId] || SOURCE_LOGO_FALLBACK;
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

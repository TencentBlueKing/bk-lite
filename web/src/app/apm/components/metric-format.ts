import dayjs from 'dayjs';
import type { CatalogStatus } from '@/app/apm/types';

/** 健康等级：1 严重 · 2 警告 · 3 关注 · 4 良好 · 5 健康 */
export type HealthLevel = 1 | 2 | 3 | 4 | 5;

export const HEALTH_DOT_CLASS: Record<HealthLevel, string> = {
  1: 'bg-[var(--color-fail)]',
  2: 'bg-[var(--theme-color-status-warning)]',
  3: 'bg-[var(--color-text-4)]',
  4: 'bg-[var(--color-text-3)]',
  5: 'bg-[var(--color-success)]',
};

export const HEALTH_LABEL: Record<HealthLevel, string> = {
  1: '严重',
  2: '警告',
  3: '关注',
  4: '良好',
  5: '健康',
};

export function deriveHealth(status: CatalogStatus, errorRate: number | null): HealthLevel {
  if (status === 'archived') return 4;
  if (status === 'silent') return 3;
  if (errorRate !== null && errorRate >= 0.05) return 1;
  if (errorRate !== null && errorRate >= 0.01) return 2;
  return 5;
}

export function formatThroughput(value: number | null, unavailable = false): string {
  if (value === null) return unavailable ? '查询失败' : '—';
  if (value >= 1000) return `${(value / 1000).toFixed(1)}k`;
  return value >= 100 ? value.toFixed(0) : value.toFixed(1);
}

export function formatErrorRate(value: number | null, unavailable = false): string {
  if (value === null) return unavailable ? '查询失败' : '—';
  const pct = value * 100;
  return `${pct.toFixed(pct >= 10 ? 1 : 2)}%`;
}

export function formatLatency(ms: number | null, unavailable = false): string {
  if (ms === null) return unavailable ? '查询失败' : '—';
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${Math.round(ms)}ms`;
}

export function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const when = dayjs(iso);
  if (!when.isValid()) return '—';
  const mins = dayjs().diff(when, 'minute');
  if (mins < 1) return '刚刚';
  if (mins < 60) return `${mins} 分钟前`;
  const hours = dayjs().diff(when, 'hour');
  if (hours < 24) return `${hours} 小时前`;
  const days = dayjs().diff(when, 'day');
  if (days < 30) return `${days} 天前`;
  return when.format('YYYY-MM-DD');
}

export function isErrorRateDanger(value: number | null): boolean {
  return value !== null && value >= 0.01;
}

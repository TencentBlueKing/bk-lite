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

/** 无样本：当前时间窗没有可用 RED 点；查询失败：接口失败，可重试 */
export function formatMetricEmpty(unavailable = false): string {
  return unavailable ? '查询失败' : '无数据';
}

export function metricEmptyHint(unavailable = false): string {
  return unavailable
    ? 'RED 指标查询失败，可点击重试'
    : '当前时间窗暂无遥测样本（无流量或尚未上报）';
}

export function formatThroughput(value: number | null, unavailable = false): string {
  if (value === null) return formatMetricEmpty(unavailable);
  if (value >= 1000) return `${(value / 1000).toFixed(1)}k`;
  return value >= 100 ? value.toFixed(0) : value.toFixed(1);
}

export function formatErrorRate(value: number | null, unavailable = false): string {
  if (value === null) return formatMetricEmpty(unavailable);
  const pct = value * 100;
  return `${pct.toFixed(pct >= 10 ? 1 : 2)}%`;
}

/** SLO 接口返回百分数本身（例如 99.9），不要再按 0-1 比例放大。 */
export function formatPercentage(value: number | string, precision = 2): string {
  return `${Number(value).toFixed(precision)}%`;
}

export function formatLatency(ms: number | null, unavailable = false): string {
  if (ms === null) return formatMetricEmpty(unavailable);
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

/** 将多个服务环境的 RED 时序按时间戳对齐，聚合成应用级吞吐与加权错误率趋势。 */
export function aggregateApplicationRedTrends(
  metrics: Array<{ timeseries?: Array<{
    timestamp: string;
    request_rate: number | null;
    error_rate: number | null;
  }> }>,
): { requestRateTrend: number[]; errorRateTrend: number[] } {
  const byTimestamp = new Map<string, {
    requestRate: number;
    errorWeighted: number;
    errorWeight: number;
  }>();

  metrics.forEach((metric) => {
    (metric.timeseries ?? []).forEach((point) => {
      const current = byTimestamp.get(point.timestamp) ?? {
        requestRate: 0,
        errorWeighted: 0,
        errorWeight: 0,
      };
      if (point.request_rate !== null && Number.isFinite(point.request_rate)) {
        current.requestRate += point.request_rate;
        if (point.error_rate !== null && Number.isFinite(point.error_rate)) {
          current.errorWeighted += point.request_rate * point.error_rate;
          current.errorWeight += point.request_rate;
        }
      }
      byTimestamp.set(point.timestamp, current);
    });
  });

  const sorted = Array.from(byTimestamp.entries()).sort(([left], [right]) => left.localeCompare(right));
  return {
    requestRateTrend: sorted.map(([, point]) => point.requestRate),
    errorRateTrend: sorted.map(([, point]) => (
      point.errorWeight > 0 ? point.errorWeighted / point.errorWeight : 0
    )),
  };
}


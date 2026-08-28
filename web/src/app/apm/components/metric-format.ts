import dayjs from 'dayjs';
import type { CatalogStatus } from '@/app/apm/types';

export type Translate = (id: string, defaultMessage?: string, values?: Record<string, string | number>) => string;

const formattingLocale = () => dayjs.locale() === 'zh-cn' ? 'zh-CN' : dayjs.locale();

export function formatNumber(value: number, minimumFractionDigits = 0, maximumFractionDigits = minimumFractionDigits): string {
  return new Intl.NumberFormat(formattingLocale(), {
    minimumFractionDigits,
    maximumFractionDigits,
  }).format(value);
}

function formatUnitValue(value: string, key: string, fallback: string, t?: Translate): string {
  return t ? t(key, fallback, { value }) : fallback.replace('{value}', value);
}

/** 健康等级：1 严重 · 2 警告 · 3 关注 · 4 良好 · 5 健康 */
export type HealthLevel = 1 | 2 | 3 | 4 | 5;

export const HEALTH_DOT_CLASS: Record<HealthLevel, string> = {
  1: 'bg-[var(--color-fail)]',
  2: 'bg-[var(--theme-color-status-warning)]',
  3: 'bg-[var(--color-text-4)]',
  4: 'bg-[var(--color-text-3)]',
  5: 'bg-[var(--color-success)]',
};

export function deriveHealth(status: CatalogStatus, errorRate: number | null): HealthLevel {
  if (status === 'archived') return 4;
  if (status === 'silent') return 3;
  if (errorRate !== null && errorRate >= 0.05) return 1;
  if (errorRate !== null && errorRate >= 0.01) return 2;
  return 5;
}

/** 无样本：当前时间窗没有可用 RED 点；查询失败：接口失败，可重试 */
export function formatMetricEmpty(unavailable = false, t?: Translate): string {
  if (t) return t(unavailable ? 'apm.common.queryFailed' : 'apm.common.noData', unavailable ? '查询失败' : '无数据');
  return unavailable ? '查询失败' : '无数据';
}

export function metricEmptyHint(unavailable = false, t?: Translate): string {
  if (t) return t(
    unavailable ? 'apm.common.metricQueryFailedHint' : 'apm.common.metricNoSamplesHint',
    unavailable ? 'RED 指标查询失败，可点击重试' : '当前时间窗暂无遥测样本（无流量或尚未上报）',
  );
  return unavailable ? 'RED 指标查询失败，可点击重试' : '当前时间窗暂无遥测样本（无流量或尚未上报）';
}

export function formatThroughput(value: number | null, unavailable = false, t?: Translate): string {
  if (value === null) return formatMetricEmpty(unavailable, t);
  if (value >= 1000) {
    return formatUnitValue(formatNumber(value / 1000, 1), 'apm.common.kiloValue', '{value}k', t);
  }
  return formatNumber(value, value >= 100 ? 0 : 1);
}

export function formatErrorRate(value: number | null, unavailable = false, t?: Translate): string {
  if (value === null) return formatMetricEmpty(unavailable, t);
  const pct = value * 100;
  return new Intl.NumberFormat(formattingLocale(), {
    style: 'percent',
    minimumFractionDigits: pct >= 10 ? 1 : 2,
    maximumFractionDigits: pct >= 10 ? 1 : 2,
  }).format(value);
}

/** SLO 接口返回百分数本身（例如 99.9），不要再按 0-1 比例放大。 */
export function formatPercentage(value: number | string, precision = 2): string {
  return new Intl.NumberFormat(formattingLocale(), {
    style: 'percent',
    minimumFractionDigits: precision,
    maximumFractionDigits: precision,
  }).format(Number(value) / 100);
}

export function formatLatency(ms: number | null, unavailable = false, t?: Translate): string {
  if (ms === null) return formatMetricEmpty(unavailable, t);
  return ms >= 1000
    ? formatUnitValue(formatNumber(ms / 1000, 2), 'apm.common.secondsValue', '{value}s', t)
    : formatUnitValue(formatNumber(Math.round(ms), 0), 'apm.common.millisecondsValue', '{value}ms', t);
}

export function formatCompactLatency(ms: number): string {
  if (ms < 1) return `${ms.toFixed(2)}ms`;
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`;
  return `${Math.round(ms)}ms`;
}

export type TopologyMetricParts = {
  total: string;
  latency: string;
  errors: string;
  hasErrors: boolean;
};

export function topologyMetricParts(input: {
  errorCount: number;
  total: number;
  p95_ms?: number | null;
}): TopologyMetricParts {
  return {
    total: formatNumber(input.total),
    latency: input.p95_ms == null ? '—' : formatCompactLatency(input.p95_ms),
    errors: formatNumber(input.errorCount),
    hasErrors: input.errorCount > 0,
  };
}

export function formatTopologyMetricLine(input: {
  errorCount: number;
  total: number;
  p95_ms?: number | null;
}): string {
  const parts = topologyMetricParts(input);
  return `${parts.total} / ${parts.latency} / ${parts.errors}`;
}

export function formatTopologyEdgeMetrics(edge: {
  sampled_calls: number;
  error_calls: number;
  p95_ms?: number | null;
}): string {
  return formatTopologyMetricLine({
    errorCount: edge.error_calls,
    total: edge.sampled_calls,
    p95_ms: edge.p95_ms,
  });
}

export function formatPerSecond(value: string, t?: Translate): string {
  return formatUnitValue(value, 'apm.common.perSecondValue', '{value}/s', t);
}

export function formatRequestRate(value: number | null, unavailable = false, t?: Translate): string {
  if (value === null) return formatMetricEmpty(unavailable, t);
  return formatUnitValue(
    formatThroughput(value, unavailable, t),
    'apm.common.requestsPerSecondValue',
    '{value} req/s',
    t,
  );
}

export function formatDateTime(iso: string | null | undefined, includeSeconds = true): string {
  if (!iso) return '—';
  const value = new Date(iso);
  if (Number.isNaN(value.getTime())) return '—';
  return new Intl.DateTimeFormat(formattingLocale(), {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: includeSeconds ? '2-digit' : undefined,
  }).format(value);
}

export function formatClockTime(iso: string | null | undefined, includeSeconds = true): string {
  if (!iso) return '—';
  const value = new Date(iso);
  if (Number.isNaN(value.getTime())) return '—';
  return new Intl.DateTimeFormat(formattingLocale(), {
    hour: '2-digit',
    minute: '2-digit',
    second: includeSeconds ? '2-digit' : undefined,
  }).format(value);
}

export function formatMonthDay(iso: string | Date | null | undefined): string {
  if (!iso) return '—';
  const value = iso instanceof Date ? iso : new Date(iso);
  if (Number.isNaN(value.getTime())) return '—';
  return new Intl.DateTimeFormat(formattingLocale(), {
    month: '2-digit',
    day: '2-digit',
  }).format(value);
}

export function formatRelativeTime(iso: string | null | undefined, t?: Translate): string {
  if (!iso) return '—';
  const when = dayjs(iso);
  if (!when.isValid()) return '—';
  const seconds = dayjs().diff(when, 'second');
  // 未来时刻（时钟偏差）和不足 5 秒都收成刚刚，避免整列被“刚刚”抹平真实分钟/小时。
  if (seconds < 5) return t ? t('apm.common.justNow', '刚刚') : '刚刚';
  if (seconds < 60) return t ? t('apm.common.secondsAgo', '{count} 秒前', { count: seconds }) : `${seconds} 秒前`;
  const mins = Math.floor(seconds / 60);
  if (mins < 60) return t ? t('apm.common.minutesAgo', '{count} 分钟前', { count: mins }) : `${mins} 分钟前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return t ? t('apm.common.hoursAgo', '{count} 小时前', { count: hours }) : `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return t ? t('apm.common.daysAgo', '{count} 天前', { count: days }) : `${days} 天前`;
  return new Intl.DateTimeFormat(formattingLocale(), {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(when.toDate());
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

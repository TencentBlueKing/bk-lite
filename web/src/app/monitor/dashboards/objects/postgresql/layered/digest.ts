import type { MetricSeries } from '../../common/simple-dashboard-core';

export type PostgresDigestLoad = 'collected' | 'not_collected' | 'query_failed';

export interface PostgresStatementRow {
  id: string;
  sql: string;
  datname: string;
  totalTimeMs: number | null;
  calls: number | null;
  rowsReturned: number | null;
  timeShare: number | null;
  avgSeconds: number | null;
  trend: Array<{ time: number; value: number }>;
}

export interface StatementDatabaseFilterOption {
  text: string;
  value: string;
}

/** 列头漏斗选项：当前结果里的库名去重排序。空名和「--」不进选项，避免造库名。 */
export const statementDatabaseFilters = (
  rows: readonly { datname: string }[]
): StatementDatabaseFilterOption[] => {
  const names = new Set<string>();
  rows.forEach((row) => {
    const name = row.datname.trim();
    if (!name || name === '--') return;
    names.add(name);
  });
  return [...names]
    .sort((left, right) => left.localeCompare(right, 'zh'))
    .map((name) => ({ text: name, value: name }));
};

/** 未选等于全部。多选是 OR。空库名只在未筛时保留。 */
export const statementMatchesDatabases = (datname: string, selected: readonly string[]) => {
  if (!selected.length) return true;
  const name = datname.trim();
  if (!name || name === '--') return false;
  return selected.includes(name);
};

export interface PostgresWaitRow {
  id: string;
  name: string;
  sessions: number | null;
  trend: Array<{ time: number; value: number }>;
}

/** 有行才是已采集。查询失败不是未采集，空成功才是未开或无点。 */
export const readPostgresDigestLoad = (
  rowsLength: number,
  series: Array<{ loadState?: string } | undefined>
): PostgresDigestLoad => {
  if (rowsLength > 0) return 'collected';
  if (series.some((item) => item?.loadState === 'error')) return 'query_failed';
  return 'not_collected';
};

interface LabeledPoints {
  id: string;
  labels: Record<string, string>;
  points: Array<{ time: number; value: number }>;
}

const labeledSeries = (
  series: MetricSeries | undefined,
  idOf: (labels: Record<string, string>) => string
): LabeledPoints[] => {
  if (!series || series.loadState !== 'success' || !series.viewData?.length) return [];
  const keys = new Set<string>();
  series.viewData.forEach((point) => {
    Object.keys(point.seriesMetrics || {}).forEach((key) => keys.add(key));
  });
  return Array.from(keys).flatMap((key) => {
    const labels = series.viewData.find((point) => point.seriesMetrics?.[key])?.seriesMetrics?.[key];
    if (!labels) return [];
    const id = idOf(labels).trim();
    if (!id) return [];
    const points = series.viewData.flatMap((point) => {
      const value = point[key];
      return typeof value === 'number' && Number.isFinite(value)
        ? [{ time: Number(point.time), value }]
        : [];
    }).filter((point) => Number.isFinite(point.time));
    if (!points.length) return [];
    return [{ id, labels, points }];
  });
};

const lastValue = (points: Array<{ time: number; value: number }>): number | null => {
  const sorted = points
    .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.value))
    .sort((left, right) => left.time - right.time);
  if (!sorted.length) return null;
  return sorted[sorted.length - 1].value;
};

const rounded = (points: Array<{ time: number; value: number }>): number | null => {
  const value = lastValue(points);
  return value == null ? null : Math.round(value);
};

const rateTrend = (points: Array<{ time: number; value: number }>, scale = 1) => {
  const sorted = [...points]
    .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.value))
    .sort((left, right) => left.time - right.time)
    .map((point) => ({ time: point.time, value: point.value * scale }));
  return sorted.length >= 2 ? sorted : [];
};

const statementId = (labels: Record<string, string>) => {
  const queryid = String(labels.queryid || '').trim();
  const datname = String(labels.datname || '').trim();
  if (queryid) return datname ? `${datname}|${queryid}` : queryid;
  return String(labels.query_text || '').trim();
};

const rank = (value: number | null) => (
  value == null || !Number.isFinite(value) ? Number.NEGATIVE_INFINITY : value
);

const ROW_LIMIT = 20;

/** 按库名和语句标识对齐耗时、次数、返回行。无序列时返回空数组。 */
export const readPostgresStatementRows = (
  timeSeries: MetricSeries | undefined,
  callSeries: MetricSeries | undefined,
  rowSeries: MetricSeries | undefined,
  rateSeries?: MetricSeries
): PostgresStatementRow[] => {
  const times = labeledSeries(timeSeries, statementId);
  const calls = labeledSeries(callSeries, statementId);
  const rows = labeledSeries(rowSeries, statementId);
  const rates = new Map(labeledSeries(rateSeries, statementId).map((item) => [item.id, item]));
  const ids = new Set([...times, ...calls, ...rows].map((item) => item.id));
  const built = Array.from(ids).flatMap((id) => {
    const time = times.find((item) => item.id === id);
    const call = calls.find((item) => item.id === id);
    const returned = rows.find((item) => item.id === id);
    const labels = time?.labels || call?.labels || returned?.labels;
    if (!labels) return [];
    const sql = String(labels.query_text || labels.queryid || id).trim();
    if (!sql) return [];
    const seconds = time ? lastValue(time.points) : null;
    return [{
      id,
      sql,
      datname: String(labels.datname || '').trim(),
      totalTimeMs: seconds == null ? null : seconds * 1000,
      calls: call ? rounded(call.points) : null,
      rowsReturned: returned ? rounded(returned.points) : null,
      timeShare: null,
      avgSeconds: null,
      trend: rateTrend(rates.get(id)?.points || [], 1000)
    }];
  });
  const totalMs = built.reduce((sum, row) => sum + (row.totalTimeMs && row.totalTimeMs > 0 ? row.totalTimeMs : 0), 0);
  return built.map((row) => ({
    ...row,
    timeShare: row.totalTimeMs == null ? null : (totalMs > 0 ? Math.max(0, row.totalTimeMs) / totalMs : 0),
    avgSeconds: row.totalTimeMs == null || row.calls == null || row.calls <= 0
      ? null
      : (row.totalTimeMs / 1000) / row.calls
  })).sort((left, right) => (
    rank(right.timeShare) - rank(left.timeShare)
    || rank(right.calls) - rank(left.calls)
    || left.id.localeCompare(right.id)
  )).slice(0, ROW_LIMIT);
};

const waitId = (labels: Record<string, string>) => {
  const event = String(labels.wait_event || '').trim();
  const type = String(labels.wait_event_type || '').trim();
  if (!event) return '';
  return type ? `${type}|${event}` : event;
};

/** 按等待类型和事件名对齐当前会话数。无序列时返回空数组。 */
export const readPostgresWaitRows = (
  sessionSeries: MetricSeries | undefined
): PostgresWaitRow[] => (
  labeledSeries(sessionSeries, waitId).flatMap((item) => {
    const event = String(item.labels.wait_event || '').trim();
    if (!event) return [];
    const type = String(item.labels.wait_event_type || '').trim();
    return [{
      id: item.id,
      name: type ? `${type} · ${event}` : event,
      sessions: rounded(item.points),
      trend: rateTrend(item.points, 1)
    }];
  }).sort((left, right) => (
    (right.sessions || 0) - (left.sessions || 0)
    || left.id.localeCompare(right.id)
  )).slice(0, ROW_LIMIT)
);

const trimDigits = (value: number, digits: number) => {
  const text = value.toFixed(digits);
  return text.replace(/\.0+$/, '').replace(/(\.\d*?)0+$/, '$1');
};

export const formatTimeShare = (ratio: number | null | undefined) => {
  if (ratio == null || !Number.isFinite(ratio)) return '--';
  return `${trimDigits(Math.max(0, ratio) * 100, 1)}%`;
};

export const formatCount = (value: number | null | undefined) => {
  if (value == null || !Number.isFinite(value)) return '--';
  return Math.round(value).toLocaleString('zh-CN');
};

export const formatAverageLatency = (seconds: number | null | undefined) => {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return '--';
  if (seconds === 0) return '0 µs';
  if (seconds < 0.001) return `${trimDigits(seconds * 1e6, seconds * 1e6 >= 10 ? 0 : 1)} µs`;
  if (seconds < 1) return `${trimDigits(seconds * 1e3, seconds * 1e3 >= 10 ? 1 : 2)} ms`;
  return `${trimDigits(seconds, seconds >= 10 ? 1 : 2)} s`;
};

export interface PostgresCollectionTarget {
  monitorObjectId?: string | number | null;
  instanceId?: string | null;
  instanceName?: string | null;
}

const collectionParam = (value: unknown) => {
  const text = value == null ? '' : String(value).trim();
  if (!text || text === '--') return '';
  return text;
};

/** 打开当前实例的采集配置，而不是停在对象列表。 */
export const postgresCollectionConfigPath = (target?: PostgresCollectionTarget | null) => {
  const objectId = collectionParam(target?.monitorObjectId);
  const instanceId = collectionParam(target?.instanceId);
  const instanceName = collectionParam(target?.instanceName);
  const params = new URLSearchParams();
  if (/^\d+$/.test(objectId)) params.set('objId', objectId);
  if (instanceId) params.set('instance_id', instanceId);
  if (instanceName) params.set('instance_name', instanceName);
  const query = params.toString();
  return query ? `/monitor/integration/asset?${query}` : '/monitor/integration/asset';
};

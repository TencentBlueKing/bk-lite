import type { ChartData } from '@/app/monitor/types';
import { formatMetricValue } from '../../../shared/utils/format';
import { normalizeDashboardKey } from '../../../shared/utils';
import { getLatestChartValue } from '../../../shared/utils/chart-data';
import { encodeInstanceIdValuesParam } from '../../../shared/utils/instance';
import { HOST_SERIES_COLOR, HOST_THRESHOLD_COLOR } from '../../host/config';
import type { MetricSeries } from '../types';
import { latestNumber, primaryChartSeries } from '../../host/layered/readings';

export const MYSQL_IA_TABS = [
  { key: 'overview', label: '概览' },
  { key: 'performance', label: '性能' },
  { key: 'replication', label: '复制' },
  { key: 'statements', label: '语句' },
  { key: 'waits', label: '等待' }
] as const;

export type MysqlIaTab = (typeof MYSQL_IA_TABS)[number]['key'];

/** 专业盘实例载荷没有采集开关，空态合并「未开」与「已开仍空」。 */
export const MYSQL_EMPTY_COPY = {
  statements: {
    title: '暂无语句数据',
    hint: '请在采集配置中开启「语句采集」，并确认实例已启用 Performance Schema，监控账号有 Performance Schema 的查询权限。若已开启，保存配置后等待至少一个采集周期。'
  },
  waits: {
    title: '暂无等待数据',
    hint: '请在采集配置中开启「等待/会话采集」，并确认实例已启用 Performance Schema，监控账号有 Performance Schema 的查询权限。若已开启，保存配置后等待至少一个采集周期。'
  }
} as const;

export const isMysqlIaTab = (value: string | null | undefined): value is MysqlIaTab => (
  MYSQL_IA_TABS.some((tab) => tab.key === value)
);

export interface MysqlStatementRow {
  id: string;
  sql: string;
  /** 窗口内耗时，毫秒。无耗时序列时为 null。 */
  totalTimeMs?: number | null;
  calls?: number | null;
  rowsExamined?: number | null;
  /** 窗口内耗时占已返回语句耗时之和。无耗时字段时为 null，不填 0。 */
  timeShare?: number | null;
  avgSeconds?: number | null;
  trend?: Array<{ time: number; value: number }>;
}

export interface MysqlWaitEventRow {
  id: string;
  name: string;
  waits?: number | null;
  timeMs?: number | null;
  /** 仅当等待序列标签里真有 digest 时填写，不靠事件名猜测。 */
  statementId?: string;
  statementIds?: string[];
  trend?: Array<{ time: number; value: number }>;
}

export type StatementColumn = 'sql' | 'timeShare' | 'calls' | 'avgSeconds' | 'rowsExamined';
export type WaitColumn = 'name' | 'waits' | 'timeMs';

const finite = (value: number | null | undefined) => (
  value == null || !Number.isFinite(value) ? null : value
);

const hasNumber = (value: number | null | undefined) => finite(value) != null;

/** 三列始终在表头。扫描行有数才出现。空值由单元格显示 `--`。 */
export const statementColumns = (rows: readonly MysqlStatementRow[]): StatementColumn[] => {
  const columns: StatementColumn[] = ['sql', 'timeShare', 'calls', 'avgSeconds'];
  if (rows.some((row) => hasNumber(row.rowsExamined))) columns.push('rowsExamined');
  return columns;
};

export const waitColumns = (rows: readonly MysqlWaitEventRow[]): WaitColumn[] => {
  const columns: WaitColumn[] = ['name'];
  if (rows.some((row) => hasNumber(row.waits))) columns.push('waits');
  if (rows.some((row) => hasNumber(row.timeMs))) columns.push('timeMs');
  return columns;
};

/** 有行才算采集。空数组是无采，不补占位行。 */
export const hasStatementCollection = (rows: readonly MysqlStatementRow[]) => rows.length > 0;

export const hasWaitCollection = (rows: readonly MysqlWaitEventRow[]) => rows.length > 0;

const DIGEST_ROW_LIMIT = 20;

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

/** 计数器在当前查询窗口内的增量。单点无法做差，退回该点读数。 */
const counterIncrease = (points: Array<{ time: number; value: number }>): number | null => {
  const sorted = points
    .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.value))
    .sort((left, right) => left.time - right.time);
  if (!sorted.length) return null;
  if (sorted.length === 1) return sorted[0].value;
  let total = 0;
  for (let index = 1; index < sorted.length; index += 1) {
    const delta = sorted[index].value - sorted[index - 1].value;
    total += delta >= 0 ? delta : sorted[index].value;
  }
  return total;
};

const roundedCount = (points: Array<{ time: number; value: number }>): number | null => {
  const value = counterIncrease(points);
  return value == null ? null : Math.round(value);
};

/** 只认 digest 标签。没有该字段就不生成语句 id，避免用事件名或文本凑关联。 */
const digestStatementId = (labels: Record<string, string>) => {
  const digest = String(labels.digest || '').trim();
  if (!digest) return '';
  const schema = String(labels.schema || '').trim();
  return schema ? `${schema}|${digest}` : digest;
};

const statementIdentity = (labels: Record<string, string>) => {
  const digest = String(labels.digest || '').trim();
  const schema = String(labels.schema || '').trim();
  if (digest) return schema ? `${schema}|${digest}` : digest;
  return String(labels.digest_text || '').trim();
};

const rank = (value: number | null | undefined) => (
  value == null || !Number.isFinite(value) ? Number.NEGATIVE_INFINITY : value
);

const sumIncrease = (items: readonly LabeledPoints[]) => {
  let total = 0;
  let any = false;
  items.forEach((item) => {
    const value = counterIncrease(item.points);
    if (value == null) return;
    any = true;
    total += value;
  });
  return any ? total : null;
};

const sumCount = (items: readonly LabeledPoints[]) => {
  const value = sumIncrease(items);
  return value == null ? null : Math.round(value);
};

/** 把语句耗时、次数、扫描行按摘要对齐成表行。无序列时返回空数组。 */
export const readMysqlStatementRows = (
  timeSeries: MetricSeries | undefined,
  callSeries: MetricSeries | undefined,
  examinedSeries: MetricSeries | undefined
): MysqlStatementRow[] => {
  const times = labeledSeries(timeSeries, statementIdentity);
  const calls = labeledSeries(callSeries, statementIdentity);
  const examined = labeledSeries(examinedSeries, statementIdentity);
  const ids = new Set([...times, ...calls, ...examined].map((item) => item.id));
  const rows = Array.from(ids).flatMap((id) => {
    const time = times.find((item) => item.id === id);
    const call = calls.find((item) => item.id === id);
    const examinedRow = examined.find((item) => item.id === id);
    const labels = time?.labels || call?.labels || examinedRow?.labels;
    if (!labels) return [];
    const sql = String(labels.digest_text || labels.digest || id).trim();
    if (!sql) return [];
    const seconds = time ? counterIncrease(time.points) : null;
    const callCount = call ? roundedCount(call.points) : null;
    const trendSource = time?.points || call?.points || [];
    return [{
      id,
      sql,
      totalTimeMs: seconds == null ? null : seconds * 1000,
      calls: callCount,
      rowsExamined: examinedRow ? roundedCount(examinedRow.points) : null,
      trend: [...trendSource]
        .sort((left, right) => left.time - right.time)
        .map((point) => ({ time: point.time, value: time ? point.value * 1000 : point.value }))
    }];
  });
  const totalMs = rows.reduce((sum, row) => sum + (row.totalTimeMs && row.totalTimeMs > 0 ? row.totalTimeMs : 0), 0);
  return rows.map((row) => ({
    ...row,
    timeShare: row.totalTimeMs == null ? null : (totalMs > 0 ? Math.max(0, row.totalTimeMs) / totalMs : 0),
    avgSeconds: row.totalTimeMs == null || row.calls == null || row.calls <= 0
      ? null
      : (row.totalTimeMs / 1000) / row.calls
  })).sort((left, right) => (
    rank(right.timeShare) - rank(left.timeShare)
    || rank(right.calls) - rank(left.calls)
    || left.id.localeCompare(right.id)
  )).slice(0, DIGEST_ROW_LIMIT);
};

const groupLabeled = (items: readonly LabeledPoints[]) => {
  const groups = new Map<string, LabeledPoints[]>();
  items.forEach((item) => {
    const list = groups.get(item.id) || [];
    list.push(item);
    groups.set(item.id, list);
  });
  return groups;
};

/** 把等待次数与耗时按事件名对齐成表行。无序列时返回空数组。 */
export const readMysqlWaitRows = (
  countSeries: MetricSeries | undefined,
  timeSeries: MetricSeries | undefined
): MysqlWaitEventRow[] => {
  const eventId = (labels: Record<string, string>) => String(labels.event_name || '').trim();
  const counts = groupLabeled(labeledSeries(countSeries, eventId));
  const times = groupLabeled(labeledSeries(timeSeries, eventId));
  const ids = new Set([...counts.keys(), ...times.keys()]);
  return Array.from(ids).flatMap((id) => {
    const countGroup = counts.get(id) || [];
    const timeGroup = times.get(id) || [];
    const labels = timeGroup[0]?.labels || countGroup[0]?.labels;
    const name = String(labels?.event_name || id).trim();
    if (!name) return [];
    const seconds = sumIncrease(timeGroup);
    const statementIds = [...new Set(
      [...timeGroup, ...countGroup].map((item) => digestStatementId(item.labels)).filter(Boolean)
    )];
    const trend = countGroup.length
      ? [...countGroup[0].points].sort((left, right) => left.time - right.time)
      : [];
    return [{
      id,
      name,
      waits: sumCount(countGroup),
      timeMs: seconds == null ? null : seconds * 1000,
      statementId: statementIds.length === 1 ? statementIds[0] : undefined,
      statementIds: statementIds.length ? statementIds : undefined,
      trend
    }];
  }).sort((left, right) => (
    (right.timeMs || 0) - (left.timeMs || 0)
    || (right.waits || 0) - (left.waits || 0)
  )).slice(0, DIGEST_ROW_LIMIT);
};

export interface MysqlOverviewReadings {
  threadsConnected: number | null;
  maxConnections: number | null;
  connectionUtilization: number | null;
  qps: number | null;
  slowPerSecond: number | null;
  bufferPoolHit: number | null;
  threadsRunning: number | null;
  uptimeSeconds: number | null;
  alertCount: number | null;
}

export const readMysqlOverview = (
  metricMap: Record<string, MetricSeries | undefined>,
  alertCount: number | null
): MysqlOverviewReadings => ({
  threadsConnected: latestNumber(metricMap.mysql_threads_connected),
  maxConnections: latestNumber(metricMap.mysql_variables_max_connections),
  connectionUtilization: latestNumber(metricMap.mysql_connection_utilization),
  qps: latestNumber(metricMap.mysql_queries_rate),
  slowPerSecond: latestNumber(metricMap.mysql_slow_queries_rate),
  bufferPoolHit: latestNumber(metricMap.mysql_buffer_pool_hit_ratio),
  threadsRunning: latestNumber(metricMap.mysql_threads_running),
  uptimeSeconds: latestNumber(metricMap.mysql_uptime),
  alertCount: finite(alertCount)
});

export interface MysqlKpiCard {
  key: 'connections' | 'qps' | 'slow' | 'bufferHit' | 'uptime' | 'alerts';
  label: string;
  value: string;
  /** 与主值同一行的辅文。不另起第三行，避免把卡撑得比主机健康卡高。 */
  subtitle?: string;
  tone?: string;
}

const formatCount = (value: number) => {
  const abs = Math.abs(value);
  if (abs < 1000) return String(Math.round(value));
  const formatted = formatMetricValue(value, 'counts');
  return `${formatted.value}${formatted.unit}`;
};

const formatRate = (value: number) => {
  const formatted = formatMetricValue(value, 'cps');
  return formatted.unit === '/s' ? formatted.value : `${formatted.value}${formatted.unit}`;
};

const formatPercent = (value: number) => `${Math.min(100, Math.max(0, value)).toFixed(1)}%`;

/** 重点关注主值只要数字。百分号写在标题括号里。 */
const formatFocusPercent = (value: number) => Math.min(100, Math.max(0, value)).toFixed(1);

const KPI_ORDER: MysqlKpiCard['key'][] = [
  'connections',
  'qps',
  'slow',
  'bufferHit',
  'uptime',
  'alerts'
];

/** 与主机运行时间同一套：1d 12h / 12h 30m。 */
const formatUptime = (seconds: number) => {
  if (!Number.isFinite(seconds) || seconds <= 0) return '0s';
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m`;
  return `${Math.floor(seconds)}s`;
};

/** 其它健康卡有采才出。运行时间始终留格，缺采只空主值，避免加载后整卡消失。 */
export const hasMysqlOverviewSample = (readings: MysqlOverviewReadings) => (
  finite(readings.threadsConnected) != null
  || finite(readings.qps) != null
  || finite(readings.slowPerSecond) != null
  || finite(readings.bufferPoolHit) != null
  || finite(readings.uptimeSeconds) != null
  || finite(readings.alertCount) != null
);

export const MYSQL_UPTIME_EMPTY = '暂无数据';

const trimDigits = (value: number, digits: number) => {
  const fixed = value.toFixed(digits);
  return fixed.replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, '');
};

/** 占比。无字段为 `--`，真实 0 为 `0%`。 */
export const formatTimeShare = (ratio: number | null | undefined) => {
  if (ratio == null || !Number.isFinite(ratio)) return '--';
  return `${trimDigits(Math.max(0, ratio) * 100, 1)}%`;
};

/** 次数。无字段为 `--`。 */
export const formatCallCount = (value: number | null | undefined) => {
  if (value == null || !Number.isFinite(value)) return '--';
  return formatCount(Math.round(value));
};

/** 平均耗时。µs / ms / s 自适应。无法计算时为 `--`。 */
export const formatAverageLatency = (seconds: number | null | undefined) => {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return '--';
  if (seconds === 0) return '0 µs';
  if (seconds < 0.001) {
    const micros = seconds * 1e6;
    return `${trimDigits(micros, micros >= 10 ? 0 : 1)} µs`;
  }
  if (seconds < 1) {
    const millis = seconds * 1e3;
    return `${trimDigits(millis, millis >= 10 ? 1 : 2)} ms`;
  }
  return `${trimDigits(seconds, seconds >= 10 ? 1 : 2)} s`;
};

/**
 * 连接 / QPS / 慢查询 / 缓冲池命中 / 告警：有采才出卡。
 * 运行时间与主机专业盘同名，格位保留；有采才出主值。
 */
export const buildMysqlOverviewKpis = (readings: MysqlOverviewReadings): MysqlKpiCard[] => {
  const cards: MysqlKpiCard[] = [];
  const connected = finite(readings.threadsConnected);
  const maxConnections = finite(readings.maxConnections);
  if (connected != null) {
    const occupancy = maxConnections != null && maxConnections > 0
      ? (connected / maxConnections) * 100
      : null;
    cards.push({
      key: 'connections',
      label: '连接',
      value: formatCount(connected),
      subtitle: occupancy == null || !Number.isFinite(occupancy)
        ? undefined
        : `上限 ${formatCount(maxConnections as number)} · 占用率 ${occupancy.toFixed(1)}%`,
      tone: HOST_SERIES_COLOR.memUsed
    });
  }

  const qps = finite(readings.qps);
  if (qps != null) {
    cards.push({
      key: 'qps',
      label: 'QPS',
      value: formatRate(qps),
      tone: HOST_SERIES_COLOR.memAvailable
    });
  }

  const slow = finite(readings.slowPerSecond);
  if (slow != null) {
    cards.push({
      key: 'slow',
      label: '慢查询',
      value: `${formatRate(slow)} 次/秒`,
      tone: slow > 0 ? HOST_THRESHOLD_COLOR.warn : undefined
    });
  }

  const hit = finite(readings.bufferPoolHit);
  if (hit != null) {
    cards.push({
      key: 'bufferHit',
      label: '缓冲池命中',
      value: formatPercent(hit),
      tone: hit >= 95 ? HOST_SERIES_COLOR.cpu : HOST_THRESHOLD_COLOR.warn
    });
  }

  const uptime = finite(readings.uptimeSeconds);
  cards.push({
    key: 'uptime',
    label: '运行时间',
    value: uptime == null ? MYSQL_UPTIME_EMPTY : formatUptime(uptime)
  });

  const alerts = finite(readings.alertCount);
  if (alerts != null) {
    cards.push({
      key: 'alerts',
      label: '告警',
      value: String(Math.max(0, Math.round(alerts))),
      tone: alerts > 0 ? 'var(--color-fail)' : 'var(--color-success)'
    });
  }

  return KPI_ORDER.flatMap((key) => cards.filter((card) => card.key === key));
};

export interface MysqlFocusCard {
  key: 'slow' | 'connections' | 'buffer' | 'active';
  label: string;
  value: string;
  delta?: string;
  deltaTone?: string;
  hint: string;
  tab: MysqlIaTab;
  anchor?: 'connections' | 'throughput' | 'buffer';
  spark?: 'slow' | 'connections' | 'buffer' | 'active';
}

const percentPointDelta = (current: number, previous: number) => {
  const delta = current - previous;
  if (!Number.isFinite(delta) || Math.abs(delta) < 0.05) return null;
  const sign = delta > 0 ? '+' : '−';
  return `较上期 ${sign}${Math.abs(delta).toFixed(1)}pt`;
};

const rateDelta = (current: number, previous: number) => {
  if (!Number.isFinite(previous) || previous === 0) return null;
  const ratio = (current - previous) / Math.abs(previous);
  if (!Number.isFinite(ratio) || Math.abs(ratio) < 0.005) return null;
  const sign = ratio > 0 ? '+' : '−';
  return `较上期 ${sign}${(Math.abs(ratio) * 100).toFixed(0)}%`;
};

export const buildMysqlFocusCards = (
  current: MysqlOverviewReadings,
  previous: Pick<MysqlOverviewReadings, 'slowPerSecond' | 'connectionUtilization' | 'bufferPoolHit'>,
  statementsCollected: boolean
): MysqlFocusCard[] => {
  const cards: MysqlFocusCard[] = [];
  const slow = finite(current.slowPerSecond);
  if (slow != null) {
    const previousSlow = finite(previous.slowPerSecond);
    const delta = previousSlow == null ? null : rateDelta(slow, previousSlow);
    cards.push({
      key: 'slow',
      label: '慢查询',
      value: formatRate(slow),
      delta: delta || undefined,
      deltaTone: delta && slow > (previousSlow || 0) ? 'var(--color-fail)' : undefined,
      hint: statementsCollected ? '查看语句' : '查看吞吐',
      tab: statementsCollected ? 'statements' : 'performance',
      anchor: statementsCollected ? undefined : 'throughput',
      spark: 'slow'
    });
  }

  const utilization = finite(current.connectionUtilization);
  if (utilization != null) {
    cards.push({
      key: 'connections',
      label: '连接使用率',
      value: formatFocusPercent(utilization),
      hint: '查看连接',
      tab: 'performance',
      anchor: 'connections',
      spark: 'connections'
    });
  }

  const hit = finite(current.bufferPoolHit);
  if (hit != null) {
    const previousHit = finite(previous.bufferPoolHit);
    const delta = previousHit == null ? null : percentPointDelta(hit, previousHit);
    cards.push({
      key: 'buffer',
      label: '缓冲池命中',
      value: formatFocusPercent(hit),
      delta: delta || undefined,
      deltaTone: delta && previousHit != null && hit < previousHit ? HOST_THRESHOLD_COLOR.warn : undefined,
      hint: '查看缓冲池',
      tab: 'performance',
      anchor: 'buffer',
      spark: 'buffer'
    });
  }

  const running = finite(current.threadsRunning);
  if (running != null) {
    const rounded = Math.round(running);
    cards.push({
      key: 'active',
      label: '活跃会话',
      value: Math.abs(running - rounded) < 0.05 ? String(rounded) : running.toFixed(1),
      hint: '查看连接',
      tab: 'performance',
      anchor: 'connections',
      spark: 'active'
    });
  }
  return cards;
};

export interface MysqlHostCandidate {
  instanceId: string;
  name: string;
  nodeId: string;
  ip: string;
  instanceIdValues: string[];
  instanceIdKeys: string[];
  monitorObjectId: string;
}

export interface MysqlInstanceLink {
  nodeId: string;
  ip: string;
}

const readableHostName = (name: string) => {
  const text = name.trim();
  return text && text !== '--' ? text : '';
};

/**
 * 只在节点或 IP 唯一命中时关联主机。对不上就不造主机名。
 */
export const matchMysqlHost = (
  instance: MysqlInstanceLink,
  hosts: readonly MysqlHostCandidate[]
): MysqlHostCandidate | null => {
  const named = hosts.filter((host) => readableHostName(host.name));
  const nodeId = instance.nodeId.trim();
  if (nodeId) {
    const byNode = named.filter((host) => host.nodeId === nodeId);
    if (byNode.length === 1) return byNode[0];
  }
  const ip = instance.ip.trim();
  if (ip) {
    const byIp = named.filter((host) => host.ip === ip);
    if (byIp.length === 1) return byIp[0];
  }
  return null;
};

const HOST_OBJECT_KEYS = ['host', 'os', '主机'];

export const isHostMonitorObject = (item: { name?: string; display_name?: string }) => {
  const name = normalizeDashboardKey(item.name);
  const displayName = normalizeDashboardKey(item.display_name);
  return HOST_OBJECT_KEYS.includes(name) || HOST_OBJECT_KEYS.includes(displayName);
};

export const buildHostDashboardHref = (host: MysqlHostCandidate | null) => {
  if (!host) return '/monitor/view/dashboard/host';
  const params = new URLSearchParams({
    monitorObjId: host.monitorObjectId,
    name: 'Host',
    monitorObjDisplayName: '主机',
    instance_id: host.instanceId,
    instance_name: host.name,
    instance_id_values: encodeInstanceIdValuesParam(host.instanceIdValues),
    instance_id_keys: host.instanceIdKeys.join(',') || 'instance_id'
  });
  return `/monitor/view/dashboard/host?${params.toString()}`;
};

const seriesPresent = (metric: MetricSeries | undefined) => (
  metric?.loadState === 'success' && Array.isArray(metric.viewData) && metric.viewData.length > 0
);

/**
 * 页头拓扑。没有从库状态行、也没有 log_slave_updates 时，
 * primary/master 等名字不打成主从。传统复制区仍用抽出时的判据。
 */
export const readMysqlHeaderIdentity = (
  metricMap: Record<string, MetricSeries | undefined>,
  instanceName: string
) => {
  const hasReplicationMetrics = seriesPresent(metricMap.mysql_slave_seconds_behind_master)
    || seriesPresent(metricMap.mysql_slave_io_running)
    || seriesPresent(metricMap.mysql_slave_sql_running);
  const logSlaveUpdates = getLatestChartValue(metricMap.mysql_variables_log_slave_updates?.viewData || []);
  const nameSaysReplica = /从库|从节点|slave|replica|secondary/.test(instanceName.toLowerCase());
  const topologyEvidence = hasReplicationMetrics || logSlaveUpdates > 0;
  const replicaByWeakName = !hasReplicationMetrics && logSlaveUpdates > 0 && nameSaysReplica;
  const deployment = topologyEvidence ? '主从复制' : '单节点';
  const role = hasReplicationMetrics || replicaByWeakName
    ? '从库'
    : deployment === '主从复制'
      ? '主库'
      : '独立实例';
  return { deployment, role };
};

const collectedPoints = (series: MetricSeries | undefined) => (
  series?.loadState === 'success' ? primaryChartSeries(series.viewData) : []
);

const peakAbs = (points: ChartData[]) => {
  let peak = 0;
  let any = false;
  points.forEach((point) => {
    const value = point.value1;
    if (typeof value !== 'number' || !Number.isFinite(value)) return;
    any = true;
    peak = Math.max(peak, Math.abs(value));
  });
  return any ? peak : null;
};

/** 低于这个速率的 InnoDB 读写视为噪声，不把 Y 轴拉开放大成假波动。 */
export const INNODB_LOAD_FLOOR = 0.05;

export const innodbHasLoad = (metricMap: Record<string, MetricSeries | undefined>) => (
  [
    metricMap.mysql_innodb_data_reads_rate,
    metricMap.mysql_innodb_data_writes_rate,
    metricMap.mysql_innodb_os_log_fsyncs_rate
  ].some((series) => {
    const peak = peakAbs(collectedPoints(series));
    return peak != null && peak >= INNODB_LOAD_FLOOR;
  })
);

export type MysqlRoleTone = 'ok' | 'warn' | 'muted';

export interface MysqlRoleField {
  label: string;
  value: string;
  tone: MysqlRoleTone;
}

export interface MysqlRoleBlockModel {
  kind: 'primary' | 'replica' | 'group';
  fields: MysqlRoleField[];
  delay?: ChartData[];
}

export interface MysqlProHeader {
  pill: '主库' | '从库' | 'GR' | 'Galera';
  aside?: '写入源' | '只读';
  binlog?: 'Binlog · 已开启' | 'Binlog · 已关闭';
}

const GROUP_REPLICATION = /group_replication/i;
const GALERA = /wsrep|galera/i;
const CONNECTED_SLAVES = /connected_slaves|slaves_connected|slave_connections|replica_count|semi_sync_master_clients/i;
const SEMISYNC = /semi_?sync/i;
const BINLOG_POSITION = /binlog_(file|pos)|master_log_(file|pos)|file_position|gtid_executed/i;
const THREAD_TEXT = (value: number) => (value > 0 ? '运行中' : '已停止');
const THREAD_TONE = (value: number): MysqlRoleTone => (value > 0 ? 'ok' : 'warn');

/** 复制延迟主值。不足 1 秒用毫秒，其余用秒。 */
export const formatMysqlReplicationLag = (seconds: number) => {
  if (!Number.isFinite(seconds)) return '--';
  if (Math.abs(seconds) < 1) return `${Math.round(seconds * 1000)} 毫秒`;
  const rounded = Math.round(seconds * 10) / 10;
  const text = Math.abs(rounded - Math.round(rounded)) < 0.05
    ? String(Math.round(rounded))
    : rounded.toFixed(1);
  return `${text} 秒`;
};

const isLogBinToggle = (name: string) => /(?:^|_)log_bin$/.test(name);

const collectedNamed = (
  metricMap: Record<string, MetricSeries | undefined>,
  test: (name: string) => boolean
) => Object.entries(metricMap).flatMap(([name, series]) => {
  if (!test(name)) return [];
  const value = latestNumber(series);
  if (value == null) return [];
  return [{ name, value }];
});

const formatPlainNumber = (value: number) => {
  const rounded = Math.round(value * 100) / 100;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(2);
};

const groupFieldLabel = (name: string) => {
  if (/member_state|member_role/i.test(name)) return '成员角色';
  if (/cluster_size|member_count|members_online/i.test(name)) return '成员';
  if (/flow_control/i.test(name)) return '流控';
  if (/conflict|cert_failures/i.test(name)) return '冲突';
  return '';
};

const readonlyOn = (metricMap: Record<string, MetricSeries | undefined>) => {
  const readOnly = latestNumber(metricMap.mysql_variables_read_only);
  const superReadOnly = latestNumber(metricMap.mysql_variables_super_read_only);
  return (readOnly != null && readOnly > 0) || (superReadOnly != null && superReadOnly > 0);
};

/** 专业盘页头。Binlog 开关只出小标签；无从库线程时不伪造从库。 */
export const readMysqlProHeader = (
  metricMap: Record<string, MetricSeries | undefined>
): MysqlProHeader => {
  const gr = collectedNamed(metricMap, (name) => GROUP_REPLICATION.test(name));
  const galera = collectedNamed(metricMap, (name) => GALERA.test(name));
  const io = latestNumber(metricMap.mysql_slave_io_running);
  const sql = latestNumber(metricMap.mysql_slave_sql_running);
  const delay = latestNumber(metricMap.mysql_slave_seconds_behind_master);
  const logBin = latestNumber(metricMap.mysql_variables_log_bin);
  const pill: MysqlProHeader['pill'] = gr.length
    ? 'GR'
    : galera.length
      ? 'Galera'
      : (io != null || sql != null || delay != null)
        ? '从库'
        : '主库';
  const aside: MysqlProHeader['aside'] = pill === '主库'
    ? (readonlyOn(metricMap) ? '只读' : '写入源')
    : (readonlyOn(metricMap) ? '只读' : undefined);
  return {
    pill,
    aside,
    binlog: logBin == null ? undefined : (logBin > 0 ? 'Binlog · 已开启' : 'Binlog · 已关闭')
  };
};

const primaryDownstreamFields = (
  metricMap: Record<string, MetricSeries | undefined>
): MysqlRoleField[] => {
  const fields: MysqlRoleField[] = [];
  const seen = new Set<string>();
  Object.entries(metricMap).forEach(([name, series]) => {
    const value = latestNumber(series);
    if (value == null || isLogBinToggle(name)) return;
    const kind = CONNECTED_SLAVES.test(name)
      ? 'slaves'
      : SEMISYNC.test(name)
        ? 'semisync'
        : BINLOG_POSITION.test(name)
          ? 'position'
          : '';
    if (!kind || seen.has(kind)) return;
    seen.add(kind);
    if (kind === 'slaves') {
      fields.push({ label: '已连接从库', value: formatPlainNumber(value), tone: 'muted' });
    } else if (kind === 'semisync') {
      fields.push({
        label: '半同步',
        value: value > 0 ? '已开启' : '已关闭',
        tone: value > 0 ? 'ok' : 'muted'
      });
    } else {
      fields.push({ label: 'Binlog 位点', value: formatPlainNumber(value), tone: 'muted' });
    }
  });
  return fields;
};

/**
 * 复制状态条。无从库线程、也没有主库下游采点时返回 null。
 * 只有 log_bin 开关时同样返回 null（页头已表达）。
 * 位点、错误号和 Relay 不进这条，由 readMysqlReplicationExtras 决定。
 */
export const readMysqlRoleBlock = (
  metricMap: Record<string, MetricSeries | undefined>
): MysqlRoleBlockModel | null => {
  const groupFields = collectedNamed(
    metricMap,
    (name) => GROUP_REPLICATION.test(name) || GALERA.test(name)
  ).flatMap(({ name, value }) => {
    const label = groupFieldLabel(name);
    if (!label) return [];
    return [{ label, value: formatPlainNumber(value), tone: 'muted' as const }];
  }).slice(0, 4);
  if (groupFields.length) {
    return { kind: 'group', fields: groupFields };
  }

  const io = latestNumber(metricMap.mysql_slave_io_running);
  const sql = latestNumber(metricMap.mysql_slave_sql_running);
  const delay = latestNumber(metricMap.mysql_slave_seconds_behind_master);
  if (io != null || sql != null || delay != null) {
    const fields: MysqlRoleField[] = [];
    if (delay != null) {
      fields.push({
        label: '复制延迟',
        value: formatMysqlReplicationLag(delay),
        tone: delay > 30 ? 'warn' : 'ok'
      });
    }
    if (io != null) fields.push({ label: 'IO 线程', value: THREAD_TEXT(io), tone: THREAD_TONE(io) });
    if (sql != null) fields.push({ label: 'SQL 线程', value: THREAD_TEXT(sql), tone: THREAD_TONE(sql) });
    const delayPoints = collectedPoints(metricMap.mysql_slave_seconds_behind_master);
    return {
      kind: 'replica',
      fields,
      delay: delayPoints.length ? delayPoints : undefined
    };
  }

  const downstream = primaryDownstreamFields(metricMap);
  if (!downstream.length) return null;
  return { kind: 'primary', fields: downstream };
};

/** 专业盘复制加深查询。传统盘不加载这组。 */
export const MYSQL_REPLICATION_EXTRA_METRICS = [
  'mysql_slave_relay_log_pos',
  'mysql_slave_relay_log_space',
  'mysql_replication_source_log_pos',
  'mysql_binary_size_bytes',
  'mysql_binary_files_count',
  'mysql_slave_last_errno',
  'mysql_slave_last_io_errno',
  'mysql_slave_last_sql_errno',
  'mysql_slaves_connected',
  'mysql_rpl_semi_sync_master_clients',
  'mysql_rpl_semi_sync_master_status'
] as const;

export const MYSQL_PERF_AUX_METRICS = [
  'mysql_select_scan_rate',
  'mysql_table_locks_waited_rate'
] as const;

export const replicationExtrasPending = (
  metricMap: Record<string, MetricSeries | undefined>
) => {
  const extrasMissing = MYSQL_REPLICATION_EXTRA_METRICS.some((name) => metricMap[name] == null);
  if (!extrasMissing) return false;
  return Object.keys(metricMap).some((name) => metricMap[name] != null);
};

export interface MysqlReplicationCard {
  key: string;
  label: string;
  value: string;
  detail?: string;
  tone?: MysqlRoleTone;
}

export interface MysqlReplicationExtras {
  error: MysqlReplicationCard | null;
  logs: MysqlReplicationCard[];
  downstream: MysqlReplicationCard[];
}

const REPLICATION_ERROR_COPY: Record<number, string> = {
  1032: '找不到对应记录',
  1045: '复制账号被拒绝',
  1049: '库不存在',
  1054: '列不存在',
  1062: '主键或唯一键冲突',
  1146: '表不存在',
  1205: '锁等待超时',
  1213: '发生死锁',
  1236: '读不到主库日志',
  1396: '账号状态冲突',
  1594: '中继日志读失败',
  1872: '中继日志初始化失败',
  2003: '连不上主库'
};

const formatPosition = (value: number) => Math.round(value).toLocaleString('zh-CN');

const formatBytes = (value: number) => {
  const formatted = formatMetricValue(value, 'bytes');
  return `${formatted.value}${formatted.unit ? ` ${formatted.unit}` : ''}`;
};

const explainReplicationError = (errno: number) => REPLICATION_ERROR_COPY[errno] || '复制已报错';

const positiveErrno = (value: number | null) => (
  value != null && value > 0 ? Math.round(value) : null
);

/**
 * 复制签加深。错误号为 0 或不存在时不占卡。
 * 主库下游有采才出；从库视角不渲染主库下游。
 * 位点当前值不在这里铺文案卡，见 readMysqlReplicationSeries。
 */
export const readMysqlReplicationExtras = (
  metricMap: Record<string, MetricSeries | undefined>
): MysqlReplicationExtras => {
  const sqlErrno = positiveErrno(latestNumber(metricMap.mysql_slave_last_sql_errno));
  const ioErrno = positiveErrno(latestNumber(metricMap.mysql_slave_last_io_errno));
  const lastErrno = positiveErrno(latestNumber(metricMap.mysql_slave_last_errno));
  const primaryError = sqlErrno != null
    ? { errno: sqlErrno, thread: 'SQL 线程' }
    : ioErrno != null
      ? { errno: ioErrno, thread: 'IO 线程' }
      : lastErrno != null
        ? { errno: lastErrno, thread: '' }
        : null;
  let error: MysqlReplicationCard | null = null;
  if (primaryError) {
    const other = primaryError.thread === 'SQL 线程' && ioErrno != null && ioErrno !== primaryError.errno
      ? { errno: ioErrno, thread: 'IO 线程' }
      : primaryError.thread === 'IO 线程' && sqlErrno != null && sqlErrno !== primaryError.errno
        ? { errno: sqlErrno, thread: 'SQL 线程' }
        : null;
    const detailParts = [
      primaryError.thread,
      other ? `${other.thread}还有错误号 ${other.errno} · ${explainReplicationError(other.errno)}` : ''
    ].filter(Boolean);
    error = {
      key: 'error',
      label: '复制错误',
      value: `错误号 ${primaryError.errno} · ${explainReplicationError(primaryError.errno)}`,
      detail: detailParts.join(' · ') || undefined,
      tone: 'warn'
    };
  }

  const logs: MysqlReplicationCard[] = [];
  const relayPos = latestNumber(metricMap.mysql_slave_relay_log_pos);
  const relaySpace = latestNumber(metricMap.mysql_slave_relay_log_space);
  if (relayPos != null || relaySpace != null) {
    const parts = [
      relayPos != null ? `位置 ${formatPosition(relayPos)}` : '',
      relaySpace != null ? `空间 ${formatBytes(relaySpace)}` : ''
    ].filter(Boolean);
    logs.push({ key: 'relay', label: 'Relay 日志', value: parts.join(' · '), tone: 'muted' });
  }
  const sourcePos = latestNumber(metricMap.mysql_replication_source_log_pos);
  const binlogSize = latestNumber(metricMap.mysql_binary_size_bytes);
  const binlogFiles = latestNumber(metricMap.mysql_binary_files_count);
  if (sourcePos != null || binlogSize != null || binlogFiles != null) {
    const parts = [
      sourcePos != null ? `位置 ${formatPosition(sourcePos)}` : '',
      binlogSize != null ? `体积 ${formatBytes(binlogSize)}` : '',
      binlogFiles != null ? `${formatPosition(binlogFiles)} 个文件` : ''
    ].filter(Boolean);
    logs.push({ key: 'binlog', label: 'Binlog', value: parts.join(' · '), tone: 'muted' });
  }

  const replicaView = latestNumber(metricMap.mysql_slave_io_running) != null
    || latestNumber(metricMap.mysql_slave_sql_running) != null
    || latestNumber(metricMap.mysql_slave_seconds_behind_master) != null;
  const groupView = collectedNamed(
    metricMap,
    (name) => GROUP_REPLICATION.test(name) || GALERA.test(name)
  ).length > 0;
  const downstream: MysqlReplicationCard[] = [];
  if (!replicaView && !groupView) {
    const slaves = latestNumber(metricMap.mysql_slaves_connected);
    const clients = latestNumber(metricMap.mysql_rpl_semi_sync_master_clients);
    const count = slaves ?? clients;
    if (count != null) {
      downstream.push({
        key: 'slaves',
        label: '已连从库',
        value: formatPosition(count),
        tone: 'muted'
      });
    }
    const semisync = latestNumber(metricMap.mysql_rpl_semi_sync_master_status);
    if (semisync != null) {
      downstream.push({
        key: 'semisync',
        label: '半同步',
        value: semisync > 0 ? '已开启' : '已关闭',
        tone: semisync > 0 ? 'ok' : 'muted'
      });
    }
  }

  return { error, logs, downstream };
};

export interface MysqlReplicationSeries {
  delay: ChartData[];
  relay: ChartData[];
  binlog: ChartData[];
  delayNote?: string;
  relayNote?: string;
  binlogNote?: string;
}

const noteLine = (parts: string[]) => {
  const text = parts.filter(Boolean).join(' · ');
  return text || undefined;
};

/**
 * 复制趋势三条线：延迟、Relay 位点、Binlog 位点。
 * 体积和文件数只进标题旁注，不单独成线。没有采点就留空数组，不补 0。
 */
export const readMysqlReplicationSeries = (
  metricMap: Record<string, MetricSeries | undefined>
): MysqlReplicationSeries => {
  const delayLatest = latestNumber(metricMap.mysql_slave_seconds_behind_master);
  const relayPos = latestNumber(metricMap.mysql_slave_relay_log_pos);
  const relaySpace = latestNumber(metricMap.mysql_slave_relay_log_space);
  const sourcePos = latestNumber(metricMap.mysql_replication_source_log_pos);
  const binlogSize = latestNumber(metricMap.mysql_binary_size_bytes);
  const binlogFiles = latestNumber(metricMap.mysql_binary_files_count);
  return {
    delay: collectedPoints(metricMap.mysql_slave_seconds_behind_master),
    relay: collectedPoints(metricMap.mysql_slave_relay_log_pos),
    binlog: collectedPoints(metricMap.mysql_replication_source_log_pos),
    delayNote: delayLatest == null ? undefined : `当前 ${formatMysqlReplicationLag(delayLatest)}`,
    relayNote: noteLine([
      relayPos != null ? `位置 ${formatPosition(relayPos)}` : '',
      relaySpace != null ? formatBytes(relaySpace) : ''
    ]),
    binlogNote: noteLine([
      sourcePos != null ? `位置 ${formatPosition(sourcePos)}` : '',
      binlogSize != null ? formatBytes(binlogSize) : '',
      binlogFiles != null ? `${formatPosition(binlogFiles)} 文件` : ''
    ])
  };
};

export const waitStatementIds = (event: MysqlWaitEventRow) => {
  const ids = new Set<string>();
  event.statementIds?.forEach((id) => {
    const trimmed = id.trim();
    if (trimmed) ids.add(trimmed);
  });
  const single = event.statementId?.trim();
  if (single) ids.add(single);
  return [...ids];
};

export const waitStatementTarget = (
  event: MysqlWaitEventRow,
  statements: readonly MysqlStatementRow[]
) => {
  const match = waitStatementIds(event).find((id) => statements.some((row) => row.id === id));
  return match || null;
};

/**
 * 未选中：返回当前已加载的全部语句。
 * 选中但没有 digest 关联，或关联对不上现有语句：返回 null，由界面展示空态。
 */
export const relatedStatementRows = (
  event: MysqlWaitEventRow | null,
  statements: readonly MysqlStatementRow[]
): MysqlStatementRow[] | null => {
  if (!event) return [...statements];
  const ids = waitStatementIds(event);
  if (!ids.length) return null;
  const matched = statements.filter((row) => ids.includes(row.id));
  return matched.length ? matched : null;
};

/** 语句的主要等待。没有真实关联时返回 null，不做反向猜测。 */
export const primaryWaitForStatement = (
  statementId: string,
  waits: readonly MysqlWaitEventRow[]
): string | null => {
  const id = statementId.trim();
  if (!id) return null;
  const related = waits.filter((wait) => waitStatementIds(wait).includes(id));
  if (!related.length) return null;
  const top = [...related].sort((left, right) => (
    (right.timeMs || 0) - (left.timeMs || 0)
    || (right.waits || 0) - (left.waits || 0)
  ))[0];
  return top?.name || null;
};

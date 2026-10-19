import { formatMetricValue } from '../../../shared/utils/format';
import { normalizeDashboardKey } from '../../../shared/utils';
import { encodeInstanceIdValuesParam } from '../../../shared/utils/instance';
import { HOST_SERIES_COLOR, HOST_THRESHOLD_COLOR } from '../../host/config';
import type { MetricSeries } from '../types';
import { latestNumber } from '../../host/layered/readings';

export const MYSQL_IA_TABS = [
  { key: 'overview', label: '概览' },
  { key: 'performance', label: '性能' },
  { key: 'statements', label: '语句' },
  { key: 'waits', label: '等待' }
] as const;

export type MysqlIaTab = (typeof MYSQL_IA_TABS)[number]['key'];

export const MYSQL_EMPTY_COPY = {
  statements: {
    title: '当前实例未开启语句采集',
    hint: '开启后可在此查看 Top SQL 与趋势；详见采集配置'
  },
  waits: {
    title: '当前实例未开启等待/会话采集',
    hint: '开启后可在此查看 Wait events 并下钻到语句'
  }
} as const;

export const isMysqlIaTab = (value: string | null | undefined): value is MysqlIaTab => (
  MYSQL_IA_TABS.some((tab) => tab.key === value)
);

export interface MysqlStatementRow {
  id: string;
  sql: string;
  totalTimeMs?: number | null;
  calls?: number | null;
  rowsExamined?: number | null;
  trend?: Array<{ time: number; value: number }>;
}

export interface MysqlWaitEventRow {
  id: string;
  name: string;
  waits?: number | null;
  timeMs?: number | null;
  statementId?: string;
  trend?: Array<{ time: number; value: number }>;
}

export type StatementColumn = 'sql' | 'totalTimeMs' | 'calls' | 'rowsExamined';
export type WaitColumn = 'name' | 'waits' | 'timeMs';

const finite = (value: number | null | undefined) => (
  value == null || !Number.isFinite(value) ? null : value
);

const hasNumber = (value: number | null | undefined) => finite(value) != null;

export const statementColumns = (rows: readonly MysqlStatementRow[]): StatementColumn[] => {
  const columns: StatementColumn[] = ['sql'];
  if (rows.some((row) => hasNumber(row.totalTimeMs))) columns.push('totalTimeMs');
  if (rows.some((row) => hasNumber(row.calls))) columns.push('calls');
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

export interface MysqlOverviewReadings {
  threadsConnected: number | null;
  maxConnections: number | null;
  connectionUtilization: number | null;
  qps: number | null;
  slowPerSecond: number | null;
  bufferPoolHit: number | null;
  threadsRunning: number | null;
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
  alertCount: finite(alertCount)
});

export interface MysqlKpiCard {
  key: 'connections' | 'qps' | 'slow' | 'bufferHit' | 'active' | 'alerts';
  label: string;
  value: string;
  detail?: string;
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

const KPI_ORDER: MysqlKpiCard['key'][] = [
  'connections',
  'qps',
  'slow',
  'bufferHit',
  'active',
  'alerts'
];

/**
 * 有采才出卡。缺指标不补「—」占位。
 * 顺序固定为：连接 / QPS / 慢查 / 缓冲池命中 / 活跃会话 / 告警。
 */
export const buildMysqlOverviewKpis = (readings: MysqlOverviewReadings): MysqlKpiCard[] => {
  const cards: MysqlKpiCard[] = [];
  const connected = finite(readings.threadsConnected);
  const maxConnections = finite(readings.maxConnections);
  const utilization = finite(readings.connectionUtilization);
  if (connected != null || utilization != null) {
    const detail: string[] = [];
    if (connected != null && maxConnections != null && maxConnections > 0) {
      detail.push(`/ ${formatCount(maxConnections)}`);
    }
    if (utilization != null) detail.push(formatPercent(utilization));
    cards.push({
      key: 'connections',
      label: '连接',
      value: connected != null ? formatCount(connected) : formatPercent(utilization as number),
      detail: detail.join(' · ') || undefined,
      tone: HOST_SERIES_COLOR.memUsed
    });
  }

  const qps = finite(readings.qps);
  if (qps != null) {
    cards.push({
      key: 'qps',
      label: 'QPS',
      value: formatRate(qps),
      detail: '吞吐',
      tone: HOST_SERIES_COLOR.memAvailable
    });
  }

  const slow = finite(readings.slowPerSecond);
  if (slow != null) {
    cards.push({
      key: 'slow',
      label: '慢查',
      value: formatRate(slow),
      detail: '速率',
      tone: slow > 0 ? HOST_THRESHOLD_COLOR.warn : undefined
    });
  }

  const hit = finite(readings.bufferPoolHit);
  if (hit != null) {
    cards.push({
      key: 'bufferHit',
      label: '缓冲池命中',
      value: formatPercent(hit),
      detail: 'InnoDB',
      tone: hit >= 95 ? HOST_SERIES_COLOR.cpu : HOST_THRESHOLD_COLOR.warn
    });
  }

  const running = finite(readings.threadsRunning);
  if (running != null) {
    const rounded = Math.round(running);
    cards.push({
      key: 'active',
      label: '活跃会话',
      value: Math.abs(running - rounded) < 0.05 ? String(rounded) : running.toFixed(1),
      detail: 'Threads_running'
    });
  }

  const alerts = finite(readings.alertCount);
  if (alerts != null) {
    cards.push({
      key: 'alerts',
      label: '告警',
      value: String(Math.max(0, Math.round(alerts))),
      detail: '本实例',
      tone: alerts > 0 ? 'var(--color-fail)' : 'var(--color-success)'
    });
  }

  return KPI_ORDER.flatMap((key) => cards.filter((card) => card.key === key));
};

export interface MysqlFocusCard {
  key: 'slow' | 'connections' | 'buffer';
  label: string;
  value: string;
  delta?: string;
  deltaTone?: string;
  hint: string;
  tab: MysqlIaTab;
  anchor?: 'connections' | 'throughput' | 'buffer';
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
      hint: statementsCollected ? '跳转「语句」' : '跳转「性能 · 吞吐」',
      tab: statementsCollected ? 'statements' : 'performance',
      anchor: statementsCollected ? undefined : 'throughput'
    });
  }

  const utilization = finite(current.connectionUtilization);
  if (utilization != null) {
    cards.push({
      key: 'connections',
      label: '连接使用率',
      value: formatPercent(utilization),
      hint: '跳转「性能 · 连接」',
      tab: 'performance',
      anchor: 'connections'
    });
  }

  const hit = finite(current.bufferPoolHit);
  if (hit != null) {
    const previousHit = finite(previous.bufferPoolHit);
    const delta = previousHit == null ? null : percentPointDelta(hit, previousHit);
    cards.push({
      key: 'buffer',
      label: '缓冲池命中',
      value: formatPercent(hit),
      delta: delta || undefined,
      deltaTone: delta && previousHit != null && hit < previousHit ? HOST_THRESHOLD_COLOR.warn : undefined,
      hint: '跳转「性能 · 缓冲池」',
      tab: 'performance',
      anchor: 'buffer'
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

export const waitStatementTarget = (
  event: MysqlWaitEventRow,
  statements: readonly MysqlStatementRow[]
) => {
  const statementId = event.statementId?.trim();
  if (!statementId) return null;
  return statements.some((row) => row.id === statementId) ? statementId : null;
};

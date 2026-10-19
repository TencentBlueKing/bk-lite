import type { ChartData } from '@/app/monitor/types';
import { formatMetricValue } from '../../../shared/utils/format';
import { normalizeDashboardKey } from '../../../shared/utils';
import { getLatestChartValue, mergeChartSeries } from '../../../shared/utils/chart-data';
import { encodeInstanceIdValuesParam } from '../../../shared/utils/instance';
import { HOST_SERIES_COLOR, HOST_THRESHOLD_COLOR } from '../../host/config';
import type { MetricUnit } from '../../../shared/types';
import type { MetricSeries } from '../types';
import { latestNumber, primaryChartSeries } from '../../host/layered/readings';

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

/**
 * 有采才出卡。缺指标不补「—」占位。
 * 顺序固定为：连接 / QPS / 慢查 / 缓冲池命中 / 运行时长 / 告警。
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

  const uptime = finite(readings.uptimeSeconds);
  if (uptime != null) {
    cards.push({
      key: 'uptime',
      label: '运行时长',
      value: formatUptime(uptime),
      detail: 'Uptime'
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
      hint: statementsCollected ? '跳转「语句」' : '跳转「性能 · 吞吐」',
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
      value: formatPercent(utilization),
      hint: '跳转「性能 · 连接」',
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
      value: formatPercent(hit),
      delta: delta || undefined,
      deltaTone: delta && previousHit != null && hit < previousHit ? HOST_THRESHOLD_COLOR.warn : undefined,
      hint: '跳转「性能 · 缓冲池」',
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
      hint: '跳转「性能 · 连接」',
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

const rateText = (value: number) => {
  const formatted = formatMetricValue(value, 'cps');
  return `${formatted.value}${formatted.unit || ''}`;
};

export interface MysqlTrendModel {
  key: string;
  title: string;
  unit: MetricUnit;
  data: ChartData[];
  legends: Array<{ label: string; color: string; reading?: string }>;
  reading?: string;
}

const singleTrend = (
  key: string,
  title: string,
  series: MetricSeries | undefined,
  unit: MetricUnit,
  color: string,
  readingOf: (value: number) => string
): MysqlTrendModel | null => {
  const points = collectedPoints(series);
  if (!points.length) return null;
  const latest = latestNumber(series);
  const reading = latest == null ? undefined : readingOf(latest);
  return {
    key,
    title,
    unit,
    data: points,
    legends: [{ label: title, color, reading }],
    reading
  };
};

const innodbTrend = (metricMap: Record<string, MetricSeries | undefined>): MysqlTrendModel | null => {
  if (!innodbHasLoad(metricMap)) return null;
  const read = collectedPoints(metricMap.mysql_innodb_data_reads_rate);
  const write = collectedPoints(metricMap.mysql_innodb_data_writes_rate);
  const data = mergeChartSeries([
    { key: 'read', label: '读', data: read },
    { key: 'write', label: '写', data: write }
  ]).filter((point) => point.value1 != null || point.value2 != null);
  if (!data.length) return null;
  const readNow = latestNumber(metricMap.mysql_innodb_data_reads_rate);
  const writeNow = latestNumber(metricMap.mysql_innodb_data_writes_rate);
  return {
    key: 'innodb',
    title: 'InnoDB 读写',
    unit: 'cps',
    data,
    legends: [
      {
        label: '读',
        color: HOST_SERIES_COLOR.diskRead,
        reading: readNow == null ? undefined : rateText(readNow)
      },
      {
        label: '写',
        color: HOST_SERIES_COLOR.diskWrite,
        reading: writeNow == null ? undefined : rateText(writeNow)
      }
    ]
  };
};

/**
 * 概览趋势。四格优先连接 / QPS / 慢查 / 缓冲池命中。
 * 缓冲池无采时，第四格改成有负载的 InnoDB 读写。噪声线不占格。
 * 第一行不足四格时，第二行再补 InnoDB 或活跃会话。
 */
export const buildMysqlOverviewTrends = (
  metricMap: Record<string, MetricSeries | undefined>
) => {
  const row = [
    singleTrend('connections', '连接', metricMap.mysql_threads_connected, 'counts', HOST_SERIES_COLOR.memUsed, (value) => formatCount(value)),
    singleTrend('qps', 'QPS', metricMap.mysql_queries_rate, 'cps', HOST_SERIES_COLOR.memAvailable, rateText),
    singleTrend('slow', '慢查', metricMap.mysql_slow_queries_rate, 'cps', HOST_SERIES_COLOR.load1, rateText)
  ].filter((chart): chart is MysqlTrendModel => chart != null);
  const buffer = singleTrend(
    'buffer',
    '缓冲池命中',
    metricMap.mysql_buffer_pool_hit_ratio,
    'percent',
    HOST_SERIES_COLOR.cpu,
    (value) => formatPercent(value)
  );
  const innodb = innodbTrend(metricMap);
  if (buffer) row.push(buffer);
  else if (innodb) row.push(innodb);

  const extra: MysqlTrendModel[] = [];
  if (row.length < 4) {
    if (innodb && !row.some((chart) => chart.key === 'innodb')) extra.push(innodb);
    const active = singleTrend(
      'active',
      '活跃会话',
      metricMap.mysql_threads_running,
      'counts',
      HOST_SERIES_COLOR.load1,
      (value) => (Math.abs(value - Math.round(value)) < 0.05 ? String(Math.round(value)) : value.toFixed(1))
    );
    if (active) extra.push(active);
  }
  return { row, extra };
};

export type MysqlRoleTone = 'ok' | 'warn' | 'muted';

export interface MysqlRoleField {
  label: string;
  value: string;
  tone: MysqlRoleTone;
}

export interface MysqlRoleBlockModel {
  kind: 'primary' | 'replica' | 'group';
  pill: string;
  summary: string;
  fields: MysqlRoleField[];
  note?: string;
  delay?: ChartData[];
}

const GROUP_METRIC = /wsrep|galera|group_replication/i;
const THREAD_TEXT = (value: number) => (value > 0 ? '运行' : '停止');
const THREAD_TONE = (value: number): MysqlRoleTone => (value > 0 ? 'ok' : 'warn');

/**
 * 专业盘角色块。没有 Group Replication / Galera 采点就不出集群块。
 * 无从库线程时按主库紧凑条降级，不画「无需复制线程」大卡。
 */
export const readMysqlRoleBlock = (
  metricMap: Record<string, MetricSeries | undefined>
): MysqlRoleBlockModel => {
  const groupFields = Object.entries(metricMap).flatMap(([name, series]) => {
    if (!GROUP_METRIC.test(name)) return [];
    const value = latestNumber(series);
    if (value == null) return [];
    return [{ label: name, value: String(Math.round(value * 100) / 100), tone: 'muted' as const }];
  }).slice(0, 4);
  if (groupFields.length) {
    return {
      kind: 'group',
      pill: '集群',
      summary: 'Group Replication / Galera',
      fields: groupFields
    };
  }

  const io = latestNumber(metricMap.mysql_slave_io_running);
  const sql = latestNumber(metricMap.mysql_slave_sql_running);
  const delay = latestNumber(metricMap.mysql_slave_seconds_behind_master);
  if (io != null || sql != null || delay != null) {
    const fields: MysqlRoleField[] = [];
    if (delay != null) {
      fields.push({
        label: '复制延迟',
        value: `${Math.round(delay)}s`,
        tone: delay > 30 ? 'warn' : 'ok'
      });
    }
    if (io != null) fields.push({ label: 'IO 线程', value: THREAD_TEXT(io), tone: THREAD_TONE(io) });
    if (sql != null) fields.push({ label: 'SQL 线程', value: THREAD_TEXT(sql), tone: THREAD_TONE(sql) });
    const delayPoints = collectedPoints(metricMap.mysql_slave_seconds_behind_master);
    return {
      kind: 'replica',
      pill: '从库',
      summary: '复制线程与延迟',
      fields,
      delay: delayPoints.length ? delayPoints : undefined
    };
  }

  const logBin = latestNumber(metricMap.mysql_variables_log_bin);
  const readOnly = latestNumber(metricMap.mysql_variables_read_only);
  const fields: MysqlRoleField[] = [];
  if (logBin != null) {
    fields.push({
      label: 'Binlog',
      value: logBin > 0 ? '已开启' : '未开启',
      tone: logBin > 0 ? 'ok' : 'muted'
    });
  }
  return {
    kind: 'primary',
    pill: '主库',
    summary: readOnly != null && readOnly > 0 ? '实例处于只读' : '当前为写入源',
    fields,
    note: '暂无从库连接数据'
  };
};

export const waitStatementTarget = (
  event: MysqlWaitEventRow,
  statements: readonly MysqlStatementRow[]
) => {
  const statementId = event.statementId?.trim();
  if (!statementId) return null;
  return statements.some((row) => row.id === statementId) ? statementId : null;
};

import type { ChartData } from '@/app/monitor/types';
import { formatMetricValue } from '../../../shared/utils/format';
import { normalizeDashboardKey } from '../../../shared/utils';
import { getLatestChartValue } from '../../../shared/utils/chart-data';
import { encodeInstanceIdValuesParam } from '../../../shared/utils/instance';
import { HOST_SERIES_COLOR, HOST_THRESHOLD_COLOR } from '../../host/config';
import type { TabAlertLevel } from '../../host/layered/tab-level';
import type { MetricSeries } from '../types';
import { latestNumber, primaryChartSeries } from '../../host/layered/readings';
import type { MysqlCategoryCopyKey } from './mysql-copy';
import { MYSQL_CATEGORY_COPY } from './mysql-copy';
import { MYSQL_ROLE_METRICS } from './section-loading';

type MysqlText = (key: MysqlCategoryCopyKey, values?: Record<string, string | number>) => string;

export const MYSQL_IA_TABS = [
  { key: 'overview', label: '概览' },
  { key: 'performance', label: '性能' },
  { key: 'replication', label: '复制' },
  { key: 'statements', label: 'Top SQL' },
  { key: 'waits', label: '等待' }
] as const;

export type MysqlIaTab = (typeof MYSQL_IA_TABS)[number]['key'];

/** 专业盘实例载荷没有采集开关，空态合并「未开」与「已开仍空」。 */
export const MYSQL_EMPTY_COPY = {
  statements: {
    title: '暂无 Top SQL 数据',
    hint: '请在采集配置中开启「Top SQL 采集」，并确认实例已启用 Performance Schema，监控账号有 Performance Schema 的查询权限。若已开启，保存配置后等待至少一个采集周期。'
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

export type MysqlDigestLoad = 'collected' | 'not_collected' | 'query_failed';

/** 有行才是已采集。查询失败不是未采集，空成功才是未开/无点。 */
export const readMysqlDigestLoad = (
  rowsLength: number,
  series: Array<{ loadState?: string } | undefined>
): MysqlDigestLoad => {
  if (rowsLength > 0) return 'collected';
  if (series.some((item) => item?.loadState === 'error')) return 'query_failed';
  return 'not_collected';
};

export const hasStatementCollection = (
  rows: readonly MysqlStatementRow[],
  series: Array<{ loadState?: string } | undefined> = []
) => readMysqlDigestLoad(rows.length, series) !== 'not_collected';

export const hasWaitCollection = (
  rows: readonly MysqlWaitEventRow[],
  series: Array<{ loadState?: string } | undefined> = []
) => readMysqlDigestLoad(rows.length, series) !== 'not_collected';

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

/** increase() 序列取窗口终点。单点也是窗口总量，不再把累计值冒充增量。 */
const windowTotal = (points: Array<{ time: number; value: number }>): number | null => {
  const sorted = points
    .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.value))
    .sort((left, right) => left.time - right.time);
  if (!sorted.length) return null;
  return sorted[sorted.length - 1].value;
};

const roundedCount = (points: Array<{ time: number; value: number }>): number | null => {
  const value = windowTotal(points);
  return value == null ? null : Math.round(value);
};

/** rate() 趋势。少于两个点无法画速率，交给界面显示「数据不足」。 */
const rateTrend = (
  points: Array<{ time: number; value: number }>,
  scale = 1
): Array<{ time: number; value: number }> => {
  const sorted = [...points]
    .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.value))
    .sort((left, right) => left.time - right.time)
    .map((point) => ({ time: point.time, value: point.value * scale }));
  return sorted.length >= 2 ? sorted : [];
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
    const value = windowTotal(item.points);
    if (value == null) return;
    any = true;
    total += value;
  });
  return any ? total : null;
};

const mergeRateTrend = (items: readonly LabeledPoints[], scale = 1) => {
  const buckets = new Map<number, number>();
  items.forEach((item) => {
    item.points.forEach((point) => {
      if (!Number.isFinite(point.time) || !Number.isFinite(point.value)) return;
      buckets.set(point.time, (buckets.get(point.time) || 0) + point.value * scale);
    });
  });
  return rateTrend(Array.from(buckets.entries()).map(([time, value]) => ({ time, value })));
};

const sumCount = (items: readonly LabeledPoints[]) => {
  const value = sumIncrease(items);
  return value == null ? null : Math.round(value);
};

/** 把语句耗时、次数、扫描行按摘要对齐成表行。无序列时返回空数组。 */
export const readMysqlStatementRows = (
  timeSeries: MetricSeries | undefined,
  callSeries: MetricSeries | undefined,
  examinedSeries: MetricSeries | undefined,
  rateSeries?: MetricSeries
): MysqlStatementRow[] => {
  const times = labeledSeries(timeSeries, statementIdentity);
  const calls = labeledSeries(callSeries, statementIdentity);
  const examined = labeledSeries(examinedSeries, statementIdentity);
  const rates = groupLabeled(labeledSeries(rateSeries, statementIdentity));
  const ids = new Set([...times, ...calls, ...examined].map((item) => item.id));
  const rows = Array.from(ids).flatMap((id) => {
    const time = times.find((item) => item.id === id);
    const call = calls.find((item) => item.id === id);
    const examinedRow = examined.find((item) => item.id === id);
    const labels = time?.labels || call?.labels || examinedRow?.labels;
    if (!labels) return [];
    const sql = String(labels.digest_text || labels.digest || id).trim();
    if (!sql) return [];
    const seconds = time ? windowTotal(time.points) : null;
    const callCount = call ? roundedCount(call.points) : null;
    return [{
      id,
      sql,
      totalTimeMs: seconds == null ? null : seconds * 1000,
      calls: callCount,
      rowsExamined: examinedRow ? roundedCount(examinedRow.points) : null,
      trend: mergeRateTrend(rates.get(id) || [], 1000)
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

const waitEventName = (labels: Record<string, string>) => (
  String(labels.event_name || labels.event || labels.wait_event || '').trim()
);

export const digestQueryFailed = (
  rowsLength: number,
  series: Array<{ loadState?: string; viewData?: unknown[] } | undefined>
) => readMysqlDigestLoad(rowsLength, series) === 'query_failed';

/** 把等待次数与耗时按事件名对齐成表行。相关语句只认同 event_name 下真实的 digest。 */
export const readMysqlWaitRows = (
  countSeries: MetricSeries | undefined,
  timeSeries: MetricSeries | undefined,
  rateSeries?: MetricSeries
): MysqlWaitEventRow[] => {
  const eventId = waitEventName;
  const counts = groupLabeled(labeledSeries(countSeries, eventId));
  const times = groupLabeled(labeledSeries(timeSeries, eventId));
  const rates = groupLabeled(labeledSeries(rateSeries, eventId));
  const ids = new Set([...counts.keys(), ...times.keys()]);
  return Array.from(ids).flatMap((id) => {
    const countGroup = counts.get(id) || [];
    const timeGroup = times.get(id) || [];
    const labels = timeGroup[0]?.labels || countGroup[0]?.labels;
    const name = String(labels ? waitEventName(labels) : id).trim();
    if (!name) return [];
    const seconds = sumIncrease(timeGroup);
    const statementIds = [...new Set(
      [...timeGroup, ...countGroup].map((item) => digestStatementId(item.labels)).filter(Boolean)
    )];
    return [{
      id,
      name,
      waits: sumCount(countGroup),
      timeMs: seconds == null ? null : seconds * 1000,
      statementId: statementIds.length === 1 ? statementIds[0] : undefined,
      statementIds: statementIds.length ? statementIds : undefined,
      trend: mergeRateTrend(rates.get(id) || [], 1000)
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

export const REPL_LAG_WARN_S = 30;
export const REPL_LAG_CRIT_S = 300;
const MUTED_VALUE = 'var(--color-text-3)';
const EMPTY_VALUE = '—';

export interface MysqlKpiCard {
  key: 'connections' | 'qps' | 'slow' | 'replication' | 'uptime' | 'alerts';
  label: string;
  value: string;
  /** 与主值同一行的辅文。不另起第三行，避免把卡撑得比主机健康卡高。 */
  subtitle?: string;
  tone?: string;
  alertLevel?: TabAlertLevel;
  clickable?: boolean;
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

const KPI_ORDER: MysqlKpiCard['key'][] = [
  'connections',
  'qps',
  'slow',
  'replication',
  'uptime',
  'alerts'
];

/** 健康概览左四卡的跳转。运行时长与告警不在这里。 */
export const mysqlHealthKpiJump = (
  key: MysqlKpiCard['key']
): { tab: MysqlIaTab; anchor: string } | null => {
  if (key === 'connections') return { tab: 'performance', anchor: 'connections' };
  if (key === 'qps') return { tab: 'performance', anchor: 'throughput' };
  if (key === 'slow') return { tab: 'performance', anchor: 'scan-lock' };
  if (key === 'replication') return { tab: 'replication', anchor: 'mysql-repl-trend' };
  return null;
};

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

const joinSubtitle = (parts: Array<string | null | undefined>) => (
  parts.filter((part): part is string => Boolean(part && part.trim())).join(' · ')
);

const positiveErrno = (value: number | null) => (
  value != null && Number.isFinite(value) && value > 0 ? Math.round(value) : null
);

/** 已采样且数值不大于 0。缺采、NaN 不算停止，避免未知态冒出错误通栏。 */
const threadIsStopped = (value: number | null) => value != null && Number.isFinite(value) && value <= 0;

interface ActiveReplicaError {
  errno: number;
  thread: 'sql' | 'io' | '';
}

/**
 * 真错误：errno 必须 >0，且对应线程当前已停止。
 * IO 错只看 IO，SQL 错只看 SQL；只有 last 时，IO 或 SQL 任一已停止才算。
 * 线程恢复后残留的历史号不算。0、缺采、NaN、双线程运行中都不出通栏。
 */
const activeReplicaErrors = (
  metricMap: Record<string, MetricSeries | undefined>
): ActiveReplicaError[] => {
  const io = latestNumber(metricMap.mysql_slave_io_running);
  const sql = latestNumber(metricMap.mysql_slave_sql_running);
  const sqlErrno = positiveErrno(latestNumber(metricMap.mysql_slave_last_sql_errno));
  const ioErrno = positiveErrno(latestNumber(metricMap.mysql_slave_last_io_errno));
  const lastErrno = positiveErrno(latestNumber(metricMap.mysql_slave_last_errno));
  const errors: ActiveReplicaError[] = [];
  if (sqlErrno != null && threadIsStopped(sql)) errors.push({ errno: sqlErrno, thread: 'sql' });
  if (ioErrno != null && threadIsStopped(io)) errors.push({ errno: ioErrno, thread: 'io' });
  if (!errors.length && lastErrno != null && (threadIsStopped(io) || threadIsStopped(sql))) {
    errors.push({ errno: lastErrno, thread: '' });
  }
  return errors;
};

const replicaErrno = (metricMap: Record<string, MetricSeries | undefined>) => (
  activeReplicaErrors(metricMap)[0]?.errno ?? null
);

const replicaLagTone = (delay: number | null, stopped: boolean, errno: number | null) => {
  if (stopped || errno != null || (delay != null && delay > REPL_LAG_CRIT_S)) {
    return { tone: HOST_THRESHOLD_COLOR.crit, alertLevel: 'critical' as const };
  }
  if (delay != null && delay > REPL_LAG_WARN_S) {
    return { tone: HOST_THRESHOLD_COLOR.warn, alertLevel: 'warn' as const };
  }
  return { tone: undefined, alertLevel: 'none' as const };
};

const replicaDelayLevel = (delay: number): TabAlertLevel => {
  if (delay > REPL_LAG_CRIT_S) return 'critical';
  if (delay > REPL_LAG_WARN_S) return 'warn';
  return 'none';
};

const replicaThreadPart = (
  value: number | null,
  running: string,
  stopped: string
) => {
  if (value == null) return null;
  return value > 0 ? running : stopped;
};

/** 健康六格第 4 格。非复制实例也占格，避免和主机六卡错位。 */
export const buildMysqlReplicationKpi = (
  metricMap: Record<string, MetricSeries | undefined>,
  text: MysqlText,
  instanceName = ''
): Pick<MysqlKpiCard, 'value' | 'subtitle' | 'tone' | 'alertLevel' | 'clickable'> => {
  const units = { millisecond: text('millisecond'), second: text('second') };
  const block = readMysqlRoleBlock(metricMap);
  if (block?.kind === 'replica') {
    const io = latestNumber(metricMap.mysql_slave_io_running);
    const sql = latestNumber(metricMap.mysql_slave_sql_running);
    const delay = latestNumber(metricMap.mysql_slave_seconds_behind_master);
    const errno = replicaErrno(metricMap);
    const stopped = (io != null && io <= 0) || (sql != null && sql <= 0);
    const { tone, alertLevel } = replicaLagTone(delay, stopped, errno);
    const subtitle = joinSubtitle([
      delay == null ? text('lagUnknown') : null,
      replicaThreadPart(io, text('ioRunning'), text('ioStopped')),
      replicaThreadPart(sql, text('sqlRunning'), text('sqlStopped')),
      errno != null ? text('replicaError', { errno }) : null
    ]);
    const value = delay != null
      ? formatMysqlReplicationLag(delay, units)
      : errno != null
        ? text('replicationError')
        : stopped
          ? text('stopped')
          : text('running');
    return {
      value,
      subtitle: subtitle || undefined,
      tone,
      alertLevel: alertLevel === 'none' ? undefined : alertLevel,
      clickable: true
    };
  }
  if (block?.kind === 'group') {
    const gr = collectedNamed(metricMap, (name) => GROUP_REPLICATION.test(name));
    return {
      value: gr.length ? text('roleGr') : text('roleGalera'),
      subtitle: block.fields[0]?.value,
      clickable: true
    };
  }
  const slaves = latestNumber(metricMap.mysql_slaves_connected);
  if (slaves != null && slaves > 0) {
    return {
      value: text('rolePrimary'),
      subtitle: text('replicaCount', { n: formatCount(slaves) }),
      clickable: true
    };
  }
  if (!mysqlReplicationTabHasContent(metricMap)) {
    return replicationGapKpi(readMysqlReplicationGap(metricMap, instanceName), text);
  }
  return {
    value: text('rolePrimary'),
    clickable: true
  };
};

const replicationGapKpi = (
  gap: MysqlReplicationGap,
  text: MysqlText
): Pick<MysqlKpiCard, 'value' | 'subtitle' | 'tone' | 'alertLevel' | 'clickable'> => {
  if (gap === 'partial') {
    return {
      value: text('rolePrimary'),
      tone: MUTED_VALUE,
      clickable: true
    };
  }
  if (gap === 'not_collected') {
    return { value: text('notCollected'), tone: MUTED_VALUE, clickable: true };
  }
  if (gap === 'primary_no_slaves') {
    return {
      value: text('rolePrimary'),
      subtitle: text('noDownstream'),
      tone: MUTED_VALUE,
      clickable: true
    };
  }
  return {
    value: text('notConfigured'),
    subtitle: text('singleInstance'),
    tone: MUTED_VALUE,
    clickable: false
  };
};

const SLOW_QUERY_ALERT = /慢查询|slow[_\s-]*quer|mysql_slow/i;

/** 慢查询 KPI 的警示色只认告警文案，不认速率。 */
export const isSlowQueryAlertText = (content: string, policyName = '') => (
  SLOW_QUERY_ALERT.test(content) || SLOW_QUERY_ALERT.test(policyName)
);

/**
 * 连接 / QPS / 慢查询 / 复制 / 运行时间 / 告警：六格占位固定。
 * 缺采只空主值，避免加载后整卡消失、和主机六卡错位。
 */
export interface MysqlOverviewContext {
  instanceName?: string;
}

export const buildMysqlOverviewKpis = (
  readings: MysqlOverviewReadings,
  metricMap: Record<string, MetricSeries | undefined>,
  text: MysqlText,
  slowAlertActive = false,
  context: MysqlOverviewContext = {}
): MysqlKpiCard[] => {
  const cards: MysqlKpiCard[] = [];
  const connected = finite(readings.threadsConnected);
  const maxConnections = finite(readings.maxConnections);
  const occupancy = connected != null && maxConnections != null && maxConnections > 0
    ? (connected / maxConnections) * 100
    : null;
  cards.push({
    key: 'connections',
    label: text('kpiConnections'),
    value: connected == null ? EMPTY_VALUE : formatCount(connected),
    subtitle: occupancy == null || !Number.isFinite(occupancy)
      ? undefined
      : text('connectionSubtitle', {
        max: formatCount(maxConnections as number),
        occupancy: occupancy.toFixed(1)
      }),
    tone: connected == null ? undefined : HOST_SERIES_COLOR.memUsed
  });

  const qps = finite(readings.qps);
  cards.push({
    key: 'qps',
    label: text('kpiQps'),
    value: qps == null ? EMPTY_VALUE : formatRate(qps),
    tone: qps == null ? undefined : HOST_SERIES_COLOR.memAvailable
  });

  const slow = finite(readings.slowPerSecond);
  cards.push({
    key: 'slow',
    label: text('kpiSlow'),
    value: slow == null ? EMPTY_VALUE : text('slowPerSecond', { value: formatRate(slow) }),
    tone: slowAlertActive ? HOST_THRESHOLD_COLOR.warn : undefined
  });

  const replication = buildMysqlReplicationKpi(metricMap, text, context.instanceName || '');
  cards.push({
    key: 'replication',
    label: text('kpiReplication'),
    value: replication.value,
    subtitle: replication.subtitle,
    tone: replication.tone,
    alertLevel: replication.alertLevel,
    clickable: replication.clickable
  });

  const uptime = finite(readings.uptimeSeconds);
  cards.push({
    key: 'uptime',
    label: text('kpiUptime'),
    value: uptime == null ? text('kpiNoData') : formatUptime(uptime)
  });

  const alerts = finite(readings.alertCount);
  cards.push({
    key: 'alerts',
    label: text('kpiAlerts'),
    value: alerts == null ? EMPTY_VALUE : String(Math.max(0, Math.round(alerts))),
    tone: alerts == null
      ? undefined
      : (alerts > 0 ? 'var(--color-fail)' : 'var(--color-success)')
  });

  return KPI_ORDER.flatMap((key) => cards.filter((card) => card.key === key));
};

export type MysqlFocusSpark = 'active' | 'bufferHit' | 'rowLock' | 'tmpDisk';
export type MysqlFocusAnchor = 'connections' | 'buffer' | 'scan-lock';

export interface MysqlFocusCard {
  key: MysqlFocusSpark;
  label: string;
  value: string;
  /** 已采集的原始值。缺采没有，主值保持「—」。 */
  valueNumber?: number;
  subtitle?: string;
  tone?: string;
  delta?: string;
  deltaTone?: string;
  hint: string;
  tab: MysqlIaTab;
  anchor?: MysqlFocusAnchor;
  spark?: MysqlFocusSpark;
}

const rateDelta = (current: number, previous: number) => {
  if (!Number.isFinite(previous) || previous === 0) return null;
  const ratio = (current - previous) / Math.abs(previous);
  if (!Number.isFinite(ratio) || Math.abs(ratio) < 0.005) return null;
  const sign = ratio > 0 ? '+' : '−';
  return `较上期 ${sign}${(Math.abs(ratio) * 100).toFixed(0)}%`;
};

const focusTone = (level: TabAlertLevel) => {
  if (level === 'critical') return HOST_THRESHOLD_COLOR.crit;
  if (level === 'warn') return HOST_THRESHOLD_COLOR.warn;
  return undefined;
};

const uncollectedFocus = (
  key: MysqlFocusCard['key'],
  label: string,
  hint: string,
  tab: MysqlIaTab,
  anchor?: MysqlFocusAnchor
): MysqlFocusCard => ({
  key,
  label,
  value: EMPTY_VALUE,
  subtitle: undefined,
  hint,
  tab,
  anchor
});

const collectedFocus = (
  card: Omit<MysqlFocusCard, 'subtitle' | 'valueNumber'> & {
    valueNumber: number;
    previousNumber: number | null;
    /** 升高或降低算变差时，才把涨跌幅涂红。不传则不涂。 */
    deltaToneWhen?: 'up' | 'down';
  }
): MysqlFocusCard => {
  const delta = card.previousNumber == null ? null : rateDelta(card.valueNumber, card.previousNumber);
  const previous = card.previousNumber || 0;
  const worse = card.deltaToneWhen === 'up'
    ? card.valueNumber > previous
    : card.deltaToneWhen === 'down'
      ? card.valueNumber < previous
      : false;
  return {
    key: card.key,
    label: card.label,
    value: card.value,
    valueNumber: card.valueNumber,
    tone: card.tone,
    delta: delta || undefined,
    deltaTone: delta && worse ? 'var(--color-fail)' : undefined,
    hint: card.hint,
    tab: card.tab,
    anchor: card.anchor,
    spark: card.spark
  };
};

/** 偏低告警。查询已是 0–100 的百分数，没有另套产品阈值时用这档。 */
const bufferHitLevel = (value: number): TabAlertLevel => {
  if (value < 90) return 'critical';
  if (value < 95) return 'warn';
  return 'none';
};

const rowLockRateLevel = (value: number): TabAlertLevel => (
  value > 0 ? 'warn' : 'none'
);

const tmpDiskLevel = (value: number): TabAlertLevel => {
  if (value >= 25) return 'critical';
  if (value >= 10) return 'warn';
  return 'none';
};

/** 与重点关注 Y 轴同一套纯数字，单位只留在标题括号。 */
const formatFocusCount = (value: number) => {
  const abs = Math.abs(value);
  if (abs >= 1000) return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
  return value.toFixed(abs >= 100 ? 0 : 1).replace(/\.0$/, '');
};

const formatFocusPercent = (value: number) => formatMetricValue(value, 'percent').value;

const focusSlot = (spec: {
  key: MysqlFocusSpark;
  label: string;
  hint: string;
  anchor: MysqlFocusAnchor;
  value: number | null;
  previous: number | null;
  format: (value: number) => string;
  tone?: string;
  subtitle?: string;
  deltaToneWhen?: 'up' | 'down';
}): MysqlFocusCard => {
  if (spec.value == null) {
    return uncollectedFocus(spec.key, spec.label, spec.hint, 'performance', spec.anchor);
  }
  return {
    ...collectedFocus({
      key: spec.key,
      label: spec.label,
      value: spec.format(spec.value),
      valueNumber: spec.value,
      previousNumber: spec.previous,
      tone: spec.tone,
      hint: spec.hint,
      tab: 'performance',
      anchor: spec.anchor,
      spark: spec.key,
      deltaToneWhen: spec.deltaToneWhen
    }),
    subtitle: spec.subtitle
  };
};

/** 重点关注恒为 4 张。主从同一套，缺采占位，不让卡数跳动。 */
export const buildMysqlFocusCards = (
  metricMap: Record<string, MetricSeries | undefined>,
  previousMetricMap: Record<string, MetricSeries | undefined>,
  text: MysqlText
): MysqlFocusCard[] => {
  const active = finite(latestNumber(metricMap.mysql_threads_running));
  const bufferHit = finite(latestNumber(metricMap.mysql_buffer_pool_hit_ratio));
  const rowLock = finite(latestNumber(metricMap.mysql_innodb_row_lock_waits_rate));
  const rowLockTime = finite(latestNumber(metricMap.mysql_innodb_row_lock_time_avg));
  const tmpDisk = finite(latestNumber(metricMap.mysql_tmp_disk_table_ratio));
  const previousActive = finite(latestNumber(previousMetricMap.mysql_threads_running));
  const previousBufferHit = finite(latestNumber(previousMetricMap.mysql_buffer_pool_hit_ratio));
  const previousRowLock = finite(latestNumber(previousMetricMap.mysql_innodb_row_lock_waits_rate));
  const previousTmpDisk = finite(latestNumber(previousMetricMap.mysql_tmp_disk_table_ratio));
  const rowLockTimeText = rowLockTime == null
    ? undefined
    : text('rowLockAvg', { value: formatMetricValue(rowLockTime, 'ms').value });

  return [
    focusSlot({
      key: 'active',
      label: text('focusActive'),
      hint: text('viewConnections'),
      anchor: 'connections',
      value: active,
      previous: previousActive,
      format: formatFocusCount
    }),
    focusSlot({
      key: 'bufferHit',
      label: text('focusBuffer'),
      hint: text('viewBuffer'),
      anchor: 'buffer',
      value: bufferHit,
      previous: previousBufferHit,
      format: formatFocusPercent,
      tone: bufferHit == null ? undefined : focusTone(bufferHitLevel(bufferHit)),
      deltaToneWhen: 'down'
    }),
    focusSlot({
      key: 'rowLock',
      label: text('focusRowLock'),
      hint: text('viewScanLock'),
      anchor: 'scan-lock',
      value: rowLock,
      previous: previousRowLock,
      format: formatRate,
      tone: rowLock == null ? undefined : focusTone(rowLockRateLevel(rowLock)),
      subtitle: rowLockTimeText,
      deltaToneWhen: 'up'
    }),
    focusSlot({
      key: 'tmpDisk',
      label: text('focusTmpDisk'),
      hint: text('viewScanLock'),
      anchor: 'scan-lock',
      value: tmpDisk,
      previous: previousTmpDisk,
      format: formatFocusPercent,
      tone: tmpDisk == null ? undefined : focusTone(tmpDiskLevel(tmpDisk)),
      deltaToneWhen: 'up'
    })
  ].map((card) => (
    card.value === EMPTY_VALUE ? { ...card, subtitle: text('notCollected') } : card
  ));
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

/** 从库位点/Relay。有序列或 last 点都算在跟，不要求 IO/SQL/延迟。 */
export const replicaFollowPresent = (
  metricMap: Record<string, MetricSeries | undefined>
) => (
  latestNumber(metricMap.mysql_slave_relay_log_pos) != null
  || latestNumber(metricMap.mysql_slave_relay_log_space) != null
  || latestNumber(metricMap.mysql_replication_source_log_pos) != null
  || seriesPresent(metricMap.mysql_slave_relay_log_pos)
  || seriesPresent(metricMap.mysql_slave_relay_log_space)
  || seriesPresent(metricMap.mysql_replication_source_log_pos)
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
    || seriesPresent(metricMap.mysql_slave_sql_running)
    || replicaFollowPresent(metricMap);
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
  /** 复制延迟达档。线程卡仍用 tone，不在这里重复。 */
  alertLevel?: TabAlertLevel;
}

export interface MysqlRoleBlockModel {
  kind: 'primary' | 'replica' | 'group';
  fields: MysqlRoleField[];
  delay?: ChartData[];
}

export interface MysqlProHeader {
  pill: '主库' | '从库' | 'GR' | 'Galera' | '角色未知';
  aside?: '写入源' | '只读';
  binlog?: 'Binlog · 已开启' | 'Binlog · 已关闭';
  /** 版本，如 8.0.36 / 8.0。标签缺失或无法截取时为「未知」。 */
  version: string;
}

export const MYSQL_VERSION_UNKNOWN = '未知';
const INNODB_VERSION_LABEL = 'innodb_version';

/** innodb_version 有补丁时保留「大.小.补丁」（8.0.36），只有主次时退「大.小」。截不到返回「未知」。 */
export const formatMysqlMajorMinorVersion = (raw: string | null | undefined) => {
  const text = String(raw || '').trim();
  const match = text.match(/^(\d+)\.(\d+)(?:\.(\d+))?/);
  if (!match) return MYSQL_VERSION_UNKNOWN;
  return match[3] != null ? `${match[1]}.${match[2]}.${match[3]}` : `${match[1]}.${match[2]}`;
};

const innodbVersionFromSeries = (series: MetricSeries | undefined) => {
  if (!series || series.loadState !== 'success' || !series.viewData?.length) return '';
  for (const point of series.viewData) {
    const metrics = point.seriesMetrics;
    if (!metrics) continue;
    for (const labels of Object.values(metrics)) {
      const value = String(labels?.[INNODB_VERSION_LABEL] || '').trim();
      if (value) return value;
    }
  }
  return '';
};

/** 从已有 mysql_variables_* 序列的 innodb_version label 读版本。不另发查询。 */
export const readMysqlMajorMinorVersion = (
  metricMap: Record<string, MetricSeries | undefined>
) => {
  const named = innodbVersionFromSeries(metricMap.mysql_variables_max_connections)
    || innodbVersionFromSeries(metricMap.mysql_variables_read_only)
    || innodbVersionFromSeries(metricMap.mysql_variables_log_bin)
    || innodbVersionFromSeries(metricMap.mysql_variables_super_read_only)
    || innodbVersionFromSeries(metricMap.mysql_variables_log_slave_updates);
  if (named) return formatMysqlMajorMinorVersion(named);
  for (const [name, series] of Object.entries(metricMap)) {
    if (!name.startsWith('mysql_variables_')) continue;
    const value = innodbVersionFromSeries(series);
    if (value) return formatMysqlMajorMinorVersion(value);
  }
  return MYSQL_VERSION_UNKNOWN;
};

const GROUP_REPLICATION = /group_replication/i;
const GALERA = /wsrep|galera/i;
const CONNECTED_SLAVES = /connected_slaves|slaves_connected|slave_connections|replica_count|semi_sync_master_clients/i;
const SEMISYNC = /semi_?sync/i;
const BINLOG_POSITION = /binlog_(file|pos)|master_log_(file|pos)|file_position|gtid_executed/i;
const THREAD_TEXT = (value: number) => (value > 0 ? '运行中' : '已停止');
const THREAD_TONE = (value: number): MysqlRoleTone => (value > 0 ? 'ok' : 'warn');

/** 复制延迟主值。不足 1 秒用毫秒，其余用秒。 */
export const formatMysqlReplicationLag = (
  seconds: number,
  units?: { millisecond: string; second: string }
) => {
  if (!Number.isFinite(seconds)) return '--';
  const millisecond = units?.millisecond || '毫秒';
  const second = units?.second || '秒';
  if (Math.abs(seconds) < 1) return `${Math.round(seconds * 1000)} ${millisecond}`;
  const rounded = Math.round(seconds * 10) / 10;
  const text = Math.abs(rounded - Math.round(rounded)) < 0.05
    ? String(Math.round(rounded))
    : rounded.toFixed(1);
  return `${text} ${second}`;
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

/**
 * 专业盘实例摘要。Binlog 开关只出小标签；位点/Relay 也认从库。
 * 无 IO/SQL/延迟/位点/Relay 时不标主库：缺采从库不能写成「主库」，
 * read_only 单独只出「只读」，不得拼成「主库·只读」。
 */
export const readMysqlProHeader = (
  metricMap: Record<string, MetricSeries | undefined>
): MysqlProHeader => {
  const gr = collectedNamed(metricMap, (name) => GROUP_REPLICATION.test(name));
  const galera = collectedNamed(metricMap, (name) => GALERA.test(name));
  const io = latestNumber(metricMap.mysql_slave_io_running);
  const sql = latestNumber(metricMap.mysql_slave_sql_running);
  const delay = latestNumber(metricMap.mysql_slave_seconds_behind_master);
  const logBin = latestNumber(metricMap.mysql_variables_log_bin);
  const follow = replicaFollowPresent(metricMap);
  const replica = follow || io != null || sql != null || delay != null;
  const pill: MysqlProHeader['pill'] = gr.length
    ? 'GR'
    : galera.length
      ? 'Galera'
      : replica
        ? '从库'
        : '角色未知';
  const aside: MysqlProHeader['aside'] = readonlyOn(metricMap) ? '只读' : undefined;
  return {
    pill,
    aside,
    binlog: logBin == null ? undefined : (logBin > 0 ? 'Binlog · 已开启' : 'Binlog · 已关闭'),
    version: readMysqlMajorMinorVersion(metricMap)
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
 * 复制状态条。无从库线程、位点/Relay、也没有主库下游采点时返回 null。
 * 只有 log_bin 开关时同样返回 null（页头已表达）。
 * 线程与延迟缺采时仍标从库，由卡片空态表达，不把整段藏掉。
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
  if (io != null || sql != null || delay != null || replicaFollowPresent(metricMap)) {
    const fields: MysqlRoleField[] = [];
    if (delay != null) {
      const alertLevel = replicaDelayLevel(delay);
      fields.push({
        label: '复制延迟',
        value: formatMysqlReplicationLag(delay),
        tone: alertLevel === 'none' ? 'ok' : 'warn',
        alertLevel
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
  'mysql_innodb_row_lock_waits_rate',
  'mysql_innodb_row_lock_time_avg',
  'mysql_innodb_deadlocks_rate',
  'mysql_buffer_pool_hit_ratio',
  'mysql_buffer_pool_dirty_ratio',
  'mysql_innodb_buffer_pool_pages_dirty',
  'mysql_innodb_log_waits_rate',
  'mysql_innodb_data_fsyncs_rate',
  'mysql_max_used_connections',
  'mysql_threads_running',
  'mysql_threads_created_rate',
  'mysql_com_commit_rate',
  'mysql_com_rollback_rate',
  'mysql_tps_rate',
  'mysql_innodb_rows_read_rate',
  'mysql_innodb_rows_inserted_rate',
  'mysql_innodb_rows_updated_rate',
  'mysql_innodb_rows_deleted_rate',
  'mysql_aborted_connects_rate',
  'mysql_aborted_clients_rate',
  // 扫描与锁区仍画这两条。重点关注不再引用。
  'mysql_process_list_threads_waiting_for_lock',
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
  /** 有错通栏达档。线程已停止时为 critical，与上方线程卡同色。 */
  alertLevel?: 'warn' | 'critical';
}

export interface MysqlReplicationExtras {
  error: MysqlReplicationCard | null;
  downstream: MysqlReplicationCard[];
}

const fallbackMysqlText: MysqlText = (key, values) => {
  const template = MYSQL_CATEGORY_COPY[key][1];
  if (!values) return template;
  return template.replace(/\{(\w+)\}/g, (_match, name: string) => String(values[name] ?? ''));
};

const REPLICA_ERRNO_KEY: Record<number, MysqlCategoryCopyKey> = {
  1032: 'replicaErrno1032',
  1045: 'replicaErrno1045',
  1049: 'replicaErrno1049',
  1054: 'replicaErrno1054',
  1062: 'replicaErrno1062',
  1146: 'replicaErrno1146',
  1205: 'replicaErrno1205',
  1213: 'replicaErrno1213',
  1236: 'replicaErrno1236',
  1396: 'replicaErrno1396',
  1594: 'replicaErrno1594',
  1872: 'replicaErrno1872',
  2003: 'replicaErrno2003'
};

const explainReplicationError = (errno: number, text: MysqlText) => (
  text(REPLICA_ERRNO_KEY[errno] ?? 'replicaErrnoGeneric')
);

const replicaThreadLabel = (thread: 'sql' | 'io' | '', text: MysqlText) => {
  if (thread === 'sql') return text('sqlThread');
  if (thread === 'io') return text('ioThread');
  return '';
};

const formatPosition = (value: number) => Math.round(value).toLocaleString('zh-CN');

const formatBytes = (value: number) => {
  const formatted = formatMetricValue(value, 'bytes');
  return `${formatted.value}${formatted.unit ? ` ${formatted.unit}` : ''}`;
};

/**
 * 复制签加深。无真错误时 error 为 null，调用方不渲染通栏、不占位。
 * 副文只写仍停止的线程；运行中的线程不出现在错误文案里。
 * 主库下游有采才出；从库视角不渲染主库下游。
 * 位点走趋势卡，不在这里铺文案。
 */
export const readMysqlReplicationExtras = (
  metricMap: Record<string, MetricSeries | undefined>,
  text: MysqlText = fallbackMysqlText
): MysqlReplicationExtras => {
  const io = latestNumber(metricMap.mysql_slave_io_running);
  const sql = latestNumber(metricMap.mysql_slave_sql_running);
  const [primaryError, ...restErrors] = activeReplicaErrors(metricMap);
  let error: MysqlReplicationCard | null = null;
  if (primaryError) {
    const stopped = [
      threadIsStopped(sql) ? replicaThreadLabel('sql', text) : '',
      threadIsStopped(io) ? replicaThreadLabel('io', text) : ''
    ].filter(Boolean);
    const other = restErrors.find((item) => item.thread && item.errno !== primaryError.errno);
    const owner = replicaThreadLabel(primaryError.thread, text) || stopped.join('、');
    const detailParts = [
      owner ? text('replicaErrorStopped', { thread: owner }) : '',
      other
        ? text('replicaErrorOther', {
          thread: replicaThreadLabel(other.thread, text),
          errno: other.errno,
          reason: explainReplicationError(other.errno, text)
        })
        : ''
    ].filter(Boolean);
    error = {
      key: 'error',
      label: text('replicationError'),
      value: text('replicaErrorValue', {
        errno: primaryError.errno,
        reason: explainReplicationError(primaryError.errno, text)
      }),
      detail: detailParts.join(' · ') || undefined,
      tone: 'warn',
      alertLevel: 'critical'
    };
  }

  const replicaView = latestNumber(metricMap.mysql_slave_io_running) != null
    || latestNumber(metricMap.mysql_slave_sql_running) != null
    || latestNumber(metricMap.mysql_slave_seconds_behind_master) != null
    || replicaFollowPresent(metricMap);
  const groupView = collectedNamed(
    metricMap,
    (name) => GROUP_REPLICATION.test(name) || GALERA.test(name)
  ).length > 0;
  const downstream: MysqlReplicationCard[] = [];
  if (!replicaView && !groupView) {
    const slaves = latestNumber(metricMap.mysql_slaves_connected);
    const clients = latestNumber(metricMap.mysql_rpl_semi_sync_master_clients);
    const count = slaves ?? clients;
    if (count != null && count > 0) {
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

  return { error, downstream };
};

export interface MysqlReplicationSeries {
  delay: ChartData[];
  relay: ChartData[];
  binlog: ChartData[];
  delayNote?: string;
  relayNote?: string;
  binlogNote?: string;
}

/**
 * 复制趋势三条线：延迟、Relay 空间、Binlog 体积。
 * 位点不拿来画 Size。没有容量采点就留空数组，不补 0。
 */
export const readMysqlReplicationSeries = (
  metricMap: Record<string, MetricSeries | undefined>
): MysqlReplicationSeries => {
  const delayLatest = latestNumber(metricMap.mysql_slave_seconds_behind_master);
  const relaySpace = latestNumber(metricMap.mysql_slave_relay_log_space);
  const binlogSize = latestNumber(metricMap.mysql_binary_size_bytes);
  return {
    delay: collectedPoints(metricMap.mysql_slave_seconds_behind_master),
    relay: collectedPoints(metricMap.mysql_slave_relay_log_space),
    binlog: collectedPoints(metricMap.mysql_binary_size_bytes),
    delayNote: delayLatest == null ? undefined : formatMysqlReplicationLag(delayLatest),
    relayNote: relaySpace == null ? undefined : formatBytes(relaySpace),
    binlogNote: binlogSize == null ? undefined : formatBytes(binlogSize)
  };
};

export type MysqlReplicationTrendKey = 'delay' | 'relay' | 'binlog';

/**
 * Binlog 体积卡空态。顶栏已开、或有 binary_size/files 点，都不报「未开采集」。
 */
export const readMysqlBinlogTrendEmpty = (
  metricMap: Record<string, MetricSeries | undefined>,
  sizeLoadState?: string
): 'recentWindowEmpty' | 'binlogCollectionOff' => {
  const logBin = latestNumber(metricMap.mysql_variables_log_bin);
  const hasBinary = latestNumber(metricMap.mysql_binary_size_bytes) != null
    || latestNumber(metricMap.mysql_binary_files_count) != null;
  if (
    hasBinary
    || (logBin != null && logBin > 0)
    || sizeLoadState === 'success'
    || metricMap.mysql_binary_files_count?.loadState === 'success'
  ) {
    return 'recentWindowEmpty';
  }
  return 'binlogCollectionOff';
};

/**
 * 从库固定出延迟、Relay 空间、Binlog 体积。
 * 主库和组复制不出 Relay；Binlog 体积和延迟只在真有点时出。
 * 位点序列不在这三条里。
 */
export const visibleReplicationTrends = (
  kind: 'primary' | 'replica' | 'group' | undefined,
  trends: Pick<MysqlReplicationSeries, 'delay' | 'relay' | 'binlog'>
): MysqlReplicationTrendKey[] => {
  const replica = kind === 'replica';
  const slots: MysqlReplicationTrendKey[] = [];
  if (replica || trends.delay.length > 0) slots.push('delay');
  if (replica) slots.push('relay');
  if (replica || trends.binlog.length > 0) slots.push('binlog');
  return slots;
};

/** 复制签已经能画出状态、下游或趋势。空态角标只在这页还是空的时候出现。 */
export const mysqlReplicationTabHasContent = (
  metricMap: Record<string, MetricSeries | undefined>
) => {
  const block = readMysqlRoleBlock(metricMap);
  if (block?.kind === 'replica') return true;
  const statusBlock = block && block.kind !== 'primary' && block.fields.length > 0 ? block : null;
  const extras = readMysqlReplicationExtras(metricMap);
  const trends = readMysqlReplicationSeries(metricMap);
  const slots = visibleReplicationTrends(statusBlock?.kind, trends);
  return Boolean(statusBlock)
    || extras.error != null
    || extras.downstream.length > 0
    || slots.length > 0;
};

export type MysqlReplicationGap = 'partial' | 'not_collected' | 'primary_no_slaves' | 'unconfigured';

const nameSaysReplica = (instanceName: string) => (
  /从库|从节点|slave|replica|secondary/i.test(instanceName)
);

/**
 * 复制签画不出内容时的四态。有内容的页不走这里。
 * 1 partial：已有复制采点，但这页仍空。
 * 2 not_collected：没有复制采点，且只读、名字像从库，或页头身份是从库。
 * 3 primary_no_slaves：页头身份是主库，且没有下游采点。
 * 4 unconfigured：能接受的真单机。从库或只读不得落到这一态。
 */
export const readMysqlReplicationGap = (
  metricMap: Record<string, MetricSeries | undefined>,
  instanceName = ''
): MysqlReplicationGap => {
  const valueOf = (name: string) => latestNumber(metricMap[name]);
  const slaveThread = valueOf('mysql_slave_io_running') != null
    || valueOf('mysql_slave_sql_running') != null
    || valueOf('mysql_slave_seconds_behind_master') != null;
  const slaves = valueOf('mysql_slaves_connected');
  const semisyncClients = valueOf('mysql_rpl_semi_sync_master_clients');
  const downstream = (slaves != null && slaves > 0) || (semisyncClients != null && semisyncClients > 0);
  const semisync = valueOf('mysql_rpl_semi_sync_master_status') != null;
  const position = valueOf('mysql_slave_relay_log_pos') != null
    || valueOf('mysql_replication_source_log_pos') != null
    || collectedNamed(metricMap, (name) => BINLOG_POSITION.test(name) && !isLogBinToggle(name)).length > 0;
  const capacity = valueOf('mysql_slave_relay_log_space') != null
    || valueOf('mysql_binary_size_bytes') != null
    || valueOf('mysql_binary_files_count') != null;
  const errno = [
    valueOf('mysql_slave_last_errno'),
    valueOf('mysql_slave_last_io_errno'),
    valueOf('mysql_slave_last_sql_errno')
  ].some((errnoValue) => errnoValue != null && errnoValue > 0);
  if (slaveThread || downstream || semisync || position || capacity || errno) {
    return 'partial';
  }
  if (readonlyOn(metricMap) || nameSaysReplica(instanceName)) return 'not_collected';
  const identity = readMysqlHeaderIdentity(metricMap, instanceName);
  if (identity.role === '从库') return 'not_collected';
  const downstreamKnown = slaves != null || semisyncClients != null;
  if (identity.role === '主库' && !downstreamKnown) return 'primary_no_slaves';
  return 'unconfigured';
};

/**
 * 复制签角标。有内容或角色/加深指标还在加载时不挂。
 * 真单机挂「不支持」；未采（含旧 partial）挂「未采集」；主库无下游不挂角标。
 */
export const readMysqlReplicationTabBadge = (
  metricMap: Record<string, MetricSeries | undefined>,
  pendingMetricNames: ReadonlySet<string>,
  instanceName = ''
): MysqlReplicationGap | null => {
  if (mysqlReplicationTabHasContent(metricMap)) return null;
  const waiting = MYSQL_ROLE_METRICS.some((name) => pendingMetricNames.has(name))
    || MYSQL_REPLICATION_EXTRA_METRICS.some((name) => pendingMetricNames.has(name));
  if (waiting) return null;
  return readMysqlReplicationGap(metricMap, instanceName);
};

export interface MysqlCollectionConfigTarget {
  monitorObjectId?: string | number | null;
  instanceId?: string | null;
  instanceName?: string | null;
}

const collectionParam = (value: unknown) => {
  const text = value == null ? '' : String(value).trim();
  if (!text || text === '--') return '';
  return text;
};

/**
 * 当前实例的采集配置。
 * `/monitor/integration/asset?objId={monitorObjectId}&instance_id={instanceId}&instance_name={instanceName}`
 * 资产页读到 instance_id 后打开该实例的采集配置，而不是停在对象实例列表。
 */
export const mysqlCollectionConfigPath = (
  target?: string | number | MysqlCollectionConfigTarget | null
) => {
  const objectId = collectionParam(
    typeof target === 'object' && target ? target.monitorObjectId : target
  );
  const instanceId = typeof target === 'object' && target ? collectionParam(target.instanceId) : '';
  const instanceName = typeof target === 'object' && target ? collectionParam(target.instanceName) : '';
  const params = new URLSearchParams();
  if (/^\d+$/.test(objectId)) params.set('objId', objectId);
  if (instanceId) params.set('instance_id', instanceId);
  if (instanceName) params.set('instance_name', instanceName);
  const query = params.toString();
  return query ? `/monitor/integration/asset?${query}` : '/monitor/integration/asset';
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

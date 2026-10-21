import { describe, expect, it } from 'vitest';

import { HOST_THRESHOLD_COLOR } from '../../../host/config';
import {
  REPL_LAG_CRIT_S,
  REPL_LAG_WARN_S,
  buildMysqlFocusCards,
  buildMysqlOverviewKpis,
  type MysqlOverviewReadings
} from '../ia';
import { MYSQL_CATEGORY_COPY, type MysqlCategoryCopyKey } from '../mysql-copy';
import { MYSQL_FOCUS_METRICS, MYSQL_HEALTH_METRICS, MYSQL_ROLE_METRICS } from '../section-loading';
import type { MetricSeries } from '../../types';

const text = (key: MysqlCategoryCopyKey, values?: Record<string, string | number>) => {
  const [, fallback] = MYSQL_CATEGORY_COPY[key];
  if (!values) return fallback;
  return fallback.replace(/\{(\w+)\}/g, (_match, name: string) => String(values[name] ?? ''));
};

const gauge = (name: string, value: number): MetricSeries => ({
  name,
  display_name: name,
  description: name,
  unit: 'counts',
  query: name,
  color: '#000',
  loadState: 'success',
  viewData: [{ time: 1, value1: value }]
});

const readings: MysqlOverviewReadings = {
  threadsConnected: 12,
  maxConnections: 200,
  connectionUtilization: 6,
  qps: 3,
  slowPerSecond: 0,
  bufferPoolHit: 99,
  threadsRunning: 1,
  uptimeSeconds: 3600,
  alertCount: 0
};

const replicaMap = (lag: number, io = 1, sql = 1, extra: Record<string, MetricSeries> = {}) => ({
  mysql_slave_seconds_behind_master: gauge('mysql_slave_seconds_behind_master', lag),
  mysql_slave_io_running: gauge('mysql_slave_io_running', io),
  mysql_slave_sql_running: gauge('mysql_slave_sql_running', sql),
  ...extra
});

const replicationKpi = (metricMap: Record<string, MetricSeries | undefined>) => {
  const cards = buildMysqlOverviewKpis(readings, metricMap, text);
  expect(cards.map((card) => card.key)).toEqual([
    'connections',
    'qps',
    'slow',
    'replication',
    'uptime',
    'alerts'
  ]);
  return cards.find((card) => card.key === 'replication')!;
};

describe('mysql overview replication KPI', () => {
  it('keeps health metrics and focus lists aligned with the six-slot contract', () => {
    expect(MYSQL_HEALTH_METRICS).not.toContain('mysql_buffer_pool_hit_ratio');
    expect(MYSQL_HEALTH_METRICS).toEqual(expect.arrayContaining([...MYSQL_ROLE_METRICS]));
    expect(MYSQL_FOCUS_METRICS).toEqual([
      'mysql_process_list_threads_waiting_for_lock',
      'mysql_aborted_connects_rate',
      'mysql_aborted_clients_rate',
      'mysql_tmp_disk_table_ratio',
      'mysql_slave_seconds_behind_master',
      'mysql_table_locks_waited_rate'
    ]);
    expect(REPL_LAG_WARN_S).toBe(30);
    expect(REPL_LAG_CRIT_S).toBe(300);
  });

  it('shows a healthy replica lag with running threads', () => {
    const card = replicationKpi(replicaMap(5));
    expect(card.value).toBe('5 秒');
    expect(card.subtitle).toBe('IO 运行中 · SQL 运行中');
    expect(card.tone).toBe(HOST_THRESHOLD_COLOR.ok);
    expect(card.alertLevel).toBeUndefined();
    expect(card.clickable).toBe(true);
  });

  it('warns when replica lag is between 30s and 300s', () => {
    const card = replicationKpi(replicaMap(45));
    expect(card.value).toBe('45 秒');
    expect(card.subtitle).toBe('IO 运行中 · SQL 运行中');
    expect(card.tone).toBe(HOST_THRESHOLD_COLOR.warn);
    expect(card.alertLevel).toBe('warn');
  });

  it('marks IO stop as critical', () => {
    const card = replicationKpi(replicaMap(5, 0, 1));
    expect(card.value).toBe('5 秒');
    expect(card.subtitle).toBe('IO 已停止 · SQL 运行中');
    expect(card.tone).toBe(HOST_THRESHOLD_COLOR.crit);
    expect(card.alertLevel).toBe('critical');
  });

  it('shows primary with connected replicas', () => {
    const card = replicationKpi({
      mysql_slaves_connected: gauge('mysql_slaves_connected', 3)
    });
    expect(card.value).toBe('主库');
    expect(card.subtitle).toBe('3 个从库');
    expect(card.tone).toBeUndefined();
    expect(card.alertLevel).toBeUndefined();
    expect(card.clickable).toBe(true);
  });

  it('shows a muted non-replica slot', () => {
    const card = replicationKpi({});
    expect(card.value).toBe('未配置');
    expect(card.subtitle).toBe('单实例');
    expect(card.tone).toBe('var(--color-text-3)');
    expect(card.clickable).toBe(false);
  });
});

describe('mysql overview focus cards', () => {
  it('always returns four exception cards and switches the fourth by role', () => {
    const replica = buildMysqlFocusCards(replicaMap(12), {}, text);
    expect(replica).toHaveLength(4);
    expect(replica.map((card) => card.key)).toEqual(['lockWait', 'aborted', 'tmpDisk', 'replLag']);
    expect(replica[0].value).toBe('—');
    expect(replica[0].subtitle).toBe('未采集');
    expect(replica[3].tab).toBe('replication');
    expect(replica[3].value).toBe('12 秒');

    const primary = buildMysqlFocusCards({
      mysql_slaves_connected: gauge('mysql_slaves_connected', 2),
      mysql_table_locks_waited_rate: gauge('mysql_table_locks_waited_rate', 0.4)
    }, {}, text);
    expect(primary).toHaveLength(4);
    expect(primary[3].key).toBe('tableLock');
    expect(primary[3].tab).toBe('performance');
    expect(primary[3].anchor).toBe('scan-lock');
    expect(primary[3].tone).toBe(HOST_THRESHOLD_COLOR.warn);
  });

  it('applies lock-wait and replica-lag threshold boundaries', () => {
    const lockNone = buildMysqlFocusCards({
      mysql_process_list_threads_waiting_for_lock: gauge('mysql_process_list_threads_waiting_for_lock', 0)
    }, {}, text)[0];
    expect(lockNone.tone).toBeUndefined();

    const lockWarn = buildMysqlFocusCards({
      mysql_process_list_threads_waiting_for_lock: gauge('mysql_process_list_threads_waiting_for_lock', 1)
    }, {}, text)[0];
    expect(lockWarn.tone).toBe(HOST_THRESHOLD_COLOR.warn);

    const lockCrit = buildMysqlFocusCards({
      mysql_process_list_threads_waiting_for_lock: gauge('mysql_process_list_threads_waiting_for_lock', 5)
    }, {}, text)[0];
    expect(lockCrit.tone).toBe(HOST_THRESHOLD_COLOR.crit);

    const lagOk = buildMysqlFocusCards(replicaMap(REPL_LAG_WARN_S), {}, text)[3];
    expect(lagOk.tone).toBe(HOST_THRESHOLD_COLOR.ok);

    const lagWarn = buildMysqlFocusCards(replicaMap(REPL_LAG_WARN_S + 1), {}, text)[3];
    expect(lagWarn.tone).toBe(HOST_THRESHOLD_COLOR.warn);

    const lagCrit = buildMysqlFocusCards(replicaMap(REPL_LAG_CRIT_S + 1), {}, text)[3];
    expect(lagCrit.tone).toBe(HOST_THRESHOLD_COLOR.crit);
  });
});

import { describe, expect, it } from 'vitest';

import { HOST_THRESHOLD_COLOR } from '../../../host/config';
import {
  REPL_LAG_CRIT_S,
  REPL_LAG_WARN_S,
  buildMysqlFocusCards,
  buildMysqlOverviewKpis,
  isSlowQueryAlertText,
  readMysqlReplicationGap,
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
      'mysql_innodb_row_lock_waits_rate',
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
    const replica = buildMysqlFocusCards(replicaMap(12, 1, 1, {
      mysql_innodb_row_lock_waits_rate: gauge('mysql_innodb_row_lock_waits_rate', 0.5),
      mysql_innodb_row_lock_time_avg: gauge('mysql_innodb_row_lock_time_avg', 12)
    }), {}, text);
    expect(replica).toHaveLength(4);
    expect(replica.map((card) => card.key)).toEqual(['lockWait', 'aborted', 'tmpDisk', 'rowLock']);
    expect(replica[0].value).toBe('—');
    expect(replica[0].subtitle).toBe('未采集');
    expect(replica[3].label).toBe('行锁等待');
    expect(replica[3].tab).toBe('performance');
    expect(replica[3].anchor).toBe('scan-lock');
    expect(replica[3].hint).toBe('查看锁');
    expect(replica[3].value).toBe('0.50');
    expect(replica[3].subtitle).toBe('平均 12 ms');
    expect(replica[3].tone).toBeUndefined();

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

    const rowQuiet = buildMysqlFocusCards(replicaMap(0, 1, 1, {
      mysql_innodb_row_lock_waits_rate: gauge('mysql_innodb_row_lock_waits_rate', 0)
    }), {}, text)[3];
    expect(rowQuiet.key).toBe('rowLock');
    expect(rowQuiet.tone).toBeUndefined();

    const rowActive = buildMysqlFocusCards(replicaMap(0, 1, 1, {
      mysql_innodb_row_lock_waits_rate: gauge('mysql_innodb_row_lock_waits_rate', 1.2)
    }), {}, text)[3];
    expect(rowActive.key).toBe('rowLock');
    expect(rowActive.value).toBe('1.20');
    expect(rowActive.tone).toBeUndefined();
  });
});

describe('mysql slow query KPI', () => {
  const slowReadings: MysqlOverviewReadings = { ...readings, slowPerSecond: 1.2 };
  const slowCard = (slowAlertActive: boolean) => (
    buildMysqlOverviewKpis(slowReadings, {}, text, slowAlertActive).find((card) => card.key === 'slow')!
  );

  it('keeps a positive rate dark unless this instance has an unrecovered slow alert', () => {
    const quiet = slowCard(false);
    expect(quiet.value).toBe('1.20 次/秒');
    expect(quiet.subtitle).toBeUndefined();
    expect(quiet.tone).toBeUndefined();

    const warned = slowCard(true);
    expect(warned.value).toBe('1.20 次/秒');
    expect(warned.tone).toBe(HOST_THRESHOLD_COLOR.warn);

    expect(isSlowQueryAlertText('出现慢查询', '')).toBe(true);
    expect(isSlowQueryAlertText('', 'mysql_slow_queries')).toBe(true);
    expect(isSlowQueryAlertText('Slow query', 'threads')).toBe(true);
    expect(isSlowQueryAlertText('connection aborted', 'threads')).toBe(false);
  });
});

describe('mysql replication empty copy', () => {
  it('uses unconfigured and partial copy instead of one empty sentence', () => {
    expect(readMysqlReplicationGap({})).toBe('unconfigured');
    expect(readMysqlReplicationGap({
      mysql_slaves_connected: gauge('mysql_slaves_connected', 0),
      mysql_variables_log_bin: gauge('mysql_variables_log_bin', 1)
    })).toBe('unconfigured');
    expect(text('replicationUnconfigured')).toBe('当前未配置复制');
    expect(text('replicationUnconfiguredHint')).toBe('单机写入源；配置从库后将显示下游与位点');

    expect(readMysqlReplicationGap({
      mysql_variables_read_only: gauge('mysql_variables_read_only', 1)
    })).toBe('partial');
    expect(readMysqlReplicationGap({
      mysql_replication_source_log_pos: gauge('mysql_replication_source_log_pos', 80)
    })).toBe('partial');
    expect(text('replicationPartial')).toBe('复制指标未齐');
    expect(text('replicationPartialHint')).toBe('请确认采集已包含复制/半同步项');
  });
});

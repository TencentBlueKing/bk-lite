'use client';

import React, { useMemo } from 'react';
import type { ChartData } from '@/app/monitor/types';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import { mergeChartSeries, mergeChartSeriesAligned } from '../../../shared/utils/chart-data';
import type { MetricSeries } from '../types';
import { formatMetricValue } from '../../../shared/utils/format';
import { GrayTabEmptyState, ProSection, ThinTimeSeries } from '../../host/layered/pro-chrome';
import { HOST_PALETTE, HOST_SERIES_COLOR } from '../../host/config';
import { latestChartNumber, latestNumber, numericValue, primaryChartSeries } from '../../host/layered/readings';
import { innodbHasLoad } from './ia';
import { mysqlCategoryText } from './mysql-copy';
import pro from './pro.module.scss';

interface PerformancePaneProps {
  metricMap: Record<string, MetricSeries | undefined>;
  pendingMetricNames: ReadonlySet<string>;
}

const seriesOf = (metric: MetricSeries | undefined) => primaryChartSeries(metric?.viewData);

/** 数字 0 与数字字符串 "0" 都是采点。只有 null、空串和非有限值才算没有这个点。 */
const finiteChartValue = (point: ChartData | undefined): number | null => {
  if (!point) return null;
  const numeric = numericValue(point);
  if (numeric != null) return numeric;
  let bestIndex = Number.POSITIVE_INFINITY;
  let best: number | null = null;
  Object.entries(point).forEach(([key, raw]) => {
    if (!/^value\d+$/.test(key) || typeof raw !== 'string' || !raw.trim()) return;
    const parsed = Number(raw);
    if (!Number.isFinite(parsed)) return;
    const index = Number(key.slice(5));
    if (index < bestIndex) {
      bestIndex = index;
      best = parsed;
    }
  });
  return best;
};

const latestFiniteSample = (metric: MetricSeries | undefined): number | null => {
  if (!metric?.viewData?.length || metric.loadState === 'error') return null;
  for (let index = metric.viewData.length - 1; index >= 0; index -= 1) {
    const value = finiteChartValue(metric.viewData[index]);
    if (value != null) return value;
  }
  return null;
};

/** 全 0、单点 0 都留下。不要求至少两个点。 */
const chartPoints = (metric: MetricSeries | undefined): ChartData[] => {
  if (!metric?.viewData?.length || metric.loadState === 'error') return [];
  const result: ChartData[] = [];
  metric.viewData.forEach((point) => {
    const time = Number(point.time);
    const value = finiteChartValue(point);
    if (!Number.isFinite(time) || value == null) return;
    result.push({ time, value1: value });
  });
  return result;
};

const sumSeries = (parts: ChartData[][]): ChartData[] => {
  const buckets = new Map<number, number>();
  parts.forEach((points) => {
    points.forEach((point) => {
      const time = Number(point.time);
      const value = numericValue(point);
      if (!Number.isFinite(time) || value == null) return;
      buckets.set(time, (buckets.get(time) || 0) + value);
    });
  });
  return Array.from(buckets.entries())
    .sort((left, right) => left[0] - right[0])
    .map(([time, value]) => ({ time, value1: value }));
};

const rateReading = (metric: MetricSeries | undefined) => {
  const value = latestFiniteSample(metric);
  if (value == null) {
    if (metric?.loadState === 'success' || metric?.loadState === 'error') return '--';
    return undefined;
  }
  const formatted = formatMetricValue(value, 'cps');
  return `${formatted.value}${formatted.unit || ''}`;
};

/** 图例当前值跟已绘序列走。没有采点时用 `--`，名仍然留下。 */
const seriesReading = (points: ChartData[], unit: 'counts' | 'cps') => {
  const value = latestChartNumber(points);
  if (value == null) return '--';
  const formatted = formatMetricValue(value, unit);
  return `${formatted.value}${formatted.unit || ''}`;
};

const durationReading = (metric: MetricSeries | undefined) => {
  const value = latestNumber(metric);
  if (value == null) return undefined;
  const formatted = formatMetricValue(value, 'ms');
  return `${formatted.value}${formatted.unit || ''}`;
};

const percentReading = (metric: MetricSeries | undefined) => {
  const value = latestNumber(metric);
  if (value == null) return undefined;
  const formatted = formatMetricValue(value, 'percent');
  return `${formatted.value}${formatted.unit || ''}`;
};

export default function PerformancePane({ metricMap, pendingMetricNames }: PerformancePaneProps) {
  const { t } = useDashboardText();
  const maxUsed = useMemo(
    () => seriesOf(metricMap.mysql_max_used_connections),
    [metricMap.mysql_max_used_connections?.viewData]
  );
  const threadsCreated = useMemo(
    () => seriesOf(metricMap.mysql_threads_created_rate),
    [metricMap.mysql_threads_created_rate?.viewData]
  );
  const connection = useMemo(() => mergeChartSeriesAligned([
    { key: 'connected', label: mysqlCategoryText(t, 'currentConnections'), data: seriesOf(metricMap.mysql_threads_connected) },
    { key: 'running', label: mysqlCategoryText(t, 'activeSessions'), data: seriesOf(metricMap.mysql_threads_running) }
  ]), [
    metricMap.mysql_threads_connected?.viewData,
    metricMap.mysql_threads_running?.viewData,
    t
  ]);

  const writes = useMemo(() => ({
    insert: seriesOf(metricMap.mysql_com_insert_rate),
    update: seriesOf(metricMap.mysql_com_update_rate),
    delete: seriesOf(metricMap.mysql_com_delete_rate)
  }), [
    metricMap.mysql_com_insert_rate?.viewData,
    metricMap.mysql_com_update_rate?.viewData,
    metricMap.mysql_com_delete_rate?.viewData
  ]);

  const tpsParts = useMemo(() => ({
    commit: chartPoints(metricMap.mysql_com_commit_rate),
    rollback: chartPoints(metricMap.mysql_com_rollback_rate),
    total: chartPoints(metricMap.mysql_tps_rate)
  }), [
    metricMap.mysql_com_commit_rate?.viewData,
    metricMap.mysql_com_rollback_rate?.viewData,
    metricMap.mysql_tps_rate?.viewData
  ]);

  const tpsTotal = tpsParts.total.length
    ? tpsParts.total
    : sumSeries([tpsParts.commit, tpsParts.rollback]);

  const throughput = useMemo(() => mergeChartSeriesAligned([
    { key: 'qps', label: mysqlCategoryText(t, 'qps'), data: seriesOf(metricMap.mysql_queries_rate) },
    { key: 'tps', label: mysqlCategoryText(t, 'tps'), data: tpsTotal }
  ]), [metricMap.mysql_queries_rate?.viewData, t, tpsTotal]);

  const tpsMix = useMemo(() => mergeChartSeriesAligned([
    { key: 'commit', label: mysqlCategoryText(t, 'commit'), data: tpsParts.commit },
    { key: 'rollback', label: mysqlCategoryText(t, 'rollback'), data: tpsParts.rollback }
  ]), [t, tpsParts.commit, tpsParts.rollback]);

  const statementMix = useMemo(() => mergeChartSeries([
    { key: 'insert', label: 'INSERT', data: writes.insert },
    { key: 'update', label: 'UPDATE', data: writes.update },
    { key: 'delete', label: 'DELETE', data: writes.delete }
  ]), [writes]);

  const innodb = useMemo(() => mergeChartSeries([
    { key: 'read', label: mysqlCategoryText(t, 'innodbRead'), data: seriesOf(metricMap.mysql_innodb_data_reads_rate) },
    { key: 'write', label: mysqlCategoryText(t, 'innodbWrite'), data: seriesOf(metricMap.mysql_innodb_data_writes_rate) },
    { key: 'redo', label: mysqlCategoryText(t, 'innodbRedo'), data: seriesOf(metricMap.mysql_innodb_os_log_fsyncs_rate) }
  ]), [
    metricMap.mysql_innodb_data_reads_rate?.viewData,
    metricMap.mysql_innodb_data_writes_rate?.viewData,
    metricMap.mysql_innodb_os_log_fsyncs_rate?.viewData,
    t
  ]);

  const innodbRows = useMemo(() => mergeChartSeries([
    { key: 'read', label: mysqlCategoryText(t, 'rowsRead'), data: seriesOf(metricMap.mysql_innodb_rows_read_rate) },
    { key: 'insert', label: mysqlCategoryText(t, 'rowsInserted'), data: seriesOf(metricMap.mysql_innodb_rows_inserted_rate) },
    { key: 'update', label: mysqlCategoryText(t, 'rowsUpdated'), data: seriesOf(metricMap.mysql_innodb_rows_updated_rate) },
    { key: 'delete', label: mysqlCategoryText(t, 'rowsDeleted'), data: seriesOf(metricMap.mysql_innodb_rows_deleted_rate) }
  ]), [
    metricMap.mysql_innodb_rows_read_rate?.viewData,
    metricMap.mysql_innodb_rows_inserted_rate?.viewData,
    metricMap.mysql_innodb_rows_updated_rate?.viewData,
    metricMap.mysql_innodb_rows_deleted_rate?.viewData,
    t
  ]);

  const buffer = useMemo(() => mergeChartSeries([
    { key: 'hit', label: mysqlCategoryText(t, 'hitRate'), data: seriesOf(metricMap.mysql_buffer_pool_hit_ratio) }
  ]), [metricMap.mysql_buffer_pool_hit_ratio?.viewData, t]);
  const dirty = useMemo(
    () => seriesOf(metricMap.mysql_buffer_pool_dirty_ratio),
    [metricMap.mysql_buffer_pool_dirty_ratio?.viewData]
  );
  const deadlocks = useMemo(
    () => seriesOf(metricMap.mysql_innodb_deadlocks_rate),
    [metricMap.mysql_innodb_deadlocks_rate?.viewData]
  );

  const abortedConnects = useMemo(
    () => seriesOf(metricMap.mysql_aborted_connects_rate),
    [metricMap.mysql_aborted_connects_rate?.viewData]
  );
  const abortedClients = useMemo(
    () => seriesOf(metricMap.mysql_aborted_clients_rate),
    [metricMap.mysql_aborted_clients_rate?.viewData]
  );
  const slowQueries = useMemo(
    () => seriesOf(metricMap.mysql_slow_queries_rate),
    [metricMap.mysql_slow_queries_rate?.viewData]
  );
  const selectScan = useMemo(
    () => seriesOf(metricMap.mysql_select_scan_rate),
    [metricMap.mysql_select_scan_rate?.viewData]
  );
  const rowLockWaits = useMemo(
    () => seriesOf(metricMap.mysql_innodb_row_lock_waits_rate),
    [metricMap.mysql_innodb_row_lock_waits_rate?.viewData]
  );
  const rowLockTime = useMemo(
    () => seriesOf(metricMap.mysql_innodb_row_lock_time_avg),
    [metricMap.mysql_innodb_row_lock_time_avg?.viewData]
  );
  const scanSeries = useMemo(() => mergeChartSeriesAligned([
    { key: 'slow', label: mysqlCategoryText(t, 'kpiSlow'), data: slowQueries },
    { key: 'selectScan', label: mysqlCategoryText(t, 'selectScan'), data: selectScan }
  ]), [slowQueries, selectScan, t]);
  const lockSeries = useMemo(() => mergeChartSeriesAligned([
    { key: 'rowLockWaits', label: mysqlCategoryText(t, 'rowLockWaits'), data: rowLockWaits },
    { key: 'deadlocks', label: mysqlCategoryText(t, 'deadlocks'), data: deadlocks }
  ]), [rowLockWaits, deadlocks, t]);
  const lockWaitThreads = useMemo(
    () => seriesOf(metricMap.mysql_process_list_threads_waiting_for_lock),
    [metricMap.mysql_process_list_threads_waiting_for_lock?.viewData]
  );
  const tmpDisk = useMemo(
    () => seriesOf(metricMap.mysql_tmp_disk_table_ratio),
    [metricMap.mysql_tmp_disk_table_ratio?.viewData]
  );
  const tableLockWaits = useMemo(
    () => seriesOf(metricMap.mysql_table_locks_waited_rate),
    [metricMap.mysql_table_locks_waited_rate?.viewData]
  );
  const logWaits = useMemo(
    () => seriesOf(metricMap.mysql_innodb_log_waits_rate),
    [metricMap.mysql_innodb_log_waits_rate?.viewData]
  );
  const dirtyPages = useMemo(
    () => seriesOf(metricMap.mysql_innodb_buffer_pool_pages_dirty),
    [metricMap.mysql_innodb_buffer_pool_pages_dirty?.viewData]
  );
  const dataFsyncs = useMemo(
    () => seriesOf(metricMap.mysql_innodb_data_fsyncs_rate),
    [metricMap.mysql_innodb_data_fsyncs_rate?.viewData]
  );

  const slotLoading = (names: readonly string[], points: { length: number }) => (
    points.length === 0 && names.some((name) => pendingMetricNames.has(name))
  );
  const connectionAwaiting = slotLoading(
    ['mysql_threads_connected', 'mysql_threads_running'],
    connection
  );
  const throughputAwaiting = slotLoading(
    ['mysql_queries_rate', 'mysql_tps_rate', 'mysql_com_commit_rate', 'mysql_com_rollback_rate'],
    throughput
  );
  const tpsAwaiting = slotLoading(
    ['mysql_tps_rate', 'mysql_com_commit_rate', 'mysql_com_rollback_rate'],
    tpsMix
  );
  const writesAwaiting = slotLoading(
    ['mysql_com_insert_rate', 'mysql_com_update_rate', 'mysql_com_delete_rate'],
    statementMix
  );
  const innodbAwaiting = slotLoading(
    ['mysql_innodb_data_reads_rate', 'mysql_innodb_data_writes_rate', 'mysql_innodb_os_log_fsyncs_rate'],
    innodb
  );
  const innodbRowsAwaiting = slotLoading(
    [
      'mysql_innodb_rows_read_rate',
      'mysql_innodb_rows_inserted_rate',
      'mysql_innodb_rows_updated_rate',
      'mysql_innodb_rows_deleted_rate'
    ],
    innodbRows
  );
  const bufferAwaiting = slotLoading(['mysql_buffer_pool_hit_ratio'], buffer);
  const dirtyAwaiting = slotLoading(['mysql_buffer_pool_dirty_ratio'], dirty);
  const dirtyPagesAwaiting = slotLoading(['mysql_innodb_buffer_pool_pages_dirty'], dirtyPages);
  const dataFsyncsAwaiting = slotLoading(['mysql_innodb_data_fsyncs_rate'], dataFsyncs);
  const logWaitsAwaiting = slotLoading(['mysql_innodb_log_waits_rate'], logWaits);
  const lockWaitAwaiting = slotLoading(['mysql_process_list_threads_waiting_for_lock'], lockWaitThreads);
  const tmpDiskAwaiting = slotLoading(['mysql_tmp_disk_table_ratio'], tmpDisk);
  const tableLockAwaiting = slotLoading(['mysql_table_locks_waited_rate'], tableLockWaits);
  const scanAwaiting = slotLoading(
    ['mysql_slow_queries_rate', 'mysql_select_scan_rate'],
    scanSeries
  );
  const locksAwaiting = slotLoading(
    ['mysql_innodb_row_lock_waits_rate', 'mysql_innodb_deadlocks_rate'],
    lockSeries
  );
  const empty = mysqlCategoryText(t, 'noCollectData');

  const innodbCard = innodbHasLoad(metricMap) || innodbAwaiting ? (
    <ThinTimeSeries
      className={pro.pairFill}
      title={mysqlCategoryText(t, 'innodbRw')}
      hint={mysqlCategoryText(t, 'innodbRwHint')}
      loading={innodbAwaiting}
      unit="cps"
      data={innodb}
      legends={[
        { label: mysqlCategoryText(t, 'innodbRead'), color: HOST_SERIES_COLOR.diskRead, reading: rateReading(metricMap.mysql_innodb_data_reads_rate) },
        { label: mysqlCategoryText(t, 'innodbWrite'), color: HOST_SERIES_COLOR.diskWrite, reading: rateReading(metricMap.mysql_innodb_data_writes_rate) },
        { label: mysqlCategoryText(t, 'innodbRedoShort'), color: HOST_SERIES_COLOR.load1, reading: rateReading(metricMap.mysql_innodb_os_log_fsyncs_rate) }
      ]}
    />
  ) : (
    <div className={pro.innodbEmpty}>
      <GrayTabEmptyState
        title={innodb.length > 0 ? mysqlCategoryText(t, 'innodbQuiet') : empty}
        hint={mysqlCategoryText(t, 'innodbQuietHint')}
      />
    </div>
  );

  const showConnections = connectionAwaiting || connection.length > 0;
  const showMaxUsed = maxUsed.length > 0;
  const showThreadsCreated = threadsCreated.length > 0;
  const showThroughput = throughputAwaiting || throughput.length > 0;
  const connectionRowCount = [showConnections, showThroughput, showMaxUsed].filter(Boolean).length;
  const connectionRowClass = connectionRowCount >= 3 ? pro.perfGrid3 : `${pro.perfGrid} ${pro.perfFill}`;
  const connectionWide = connectionRowCount === 1;
  const showTps = tpsAwaiting || tpsMix.length > 0 || tpsTotal.length > 0;
  const showWrites = writesAwaiting || statementMix.length > 0;
  const showInnodb = innodbAwaiting || innodb.length > 0;
  const showInnodbRows = innodbRowsAwaiting || innodbRows.length > 0;
  const showBuffer = true;
  const showDirty = dirtyAwaiting || dirty.length > 0;
  const showDirtyPages = dirtyPagesAwaiting || dirtyPages.length > 0;
  const showDataFsyncs = dataFsyncsAwaiting || dataFsyncs.length > 0;
  const showLogWaits = logWaitsAwaiting || logWaits.length > 0;
  const showScan = scanAwaiting || scanSeries.length > 0;
  const showLocks = locksAwaiting || lockSeries.length > 0;
  const showRowLockTime = rowLockTime.length > 0;
  const mergedScanLockCount = [showScan, showLocks, showRowLockTime].filter(Boolean).length;
  const scanLockCount = 3 + (showLogWaits ? 1 : 0);
  const cardClass = (wide: boolean) => (wide ? `min-w-0 ${pro.perfWide}` : 'min-w-0');
  const writeInnodbPair = showWrites && showInnodb;
  const bufferCount = [showBuffer, showDirty, showDirtyPages, showDataFsyncs].filter(Boolean).length;

  return (
    <>
      {connectionRowCount > 0 || showThreadsCreated ? (
        <ProSection title={mysqlCategoryText(t, 'connectionsAndThroughput')}>
          {connectionRowCount > 0 ? (
          <div
            className={connectionRowClass}
            data-perf-section="connections"
            data-perf-count={connectionRowCount}
          >
            {showConnections ? (
              <div id="mysql-perf-connections" className={cardClass(connectionWide)}>
                <ThinTimeSeries
                  title={mysqlCategoryText(t, 'connectionsAndSessions')}
                  hint={mysqlCategoryText(t, 'connectionsHint')}
                  loading={connectionAwaiting}
                  unit="counts"
                  data={connection}
                  emptyText={empty}
                  keepLegend
                  legends={[
                    {
                      label: mysqlCategoryText(t, 'currentConnections'),
                      color: HOST_SERIES_COLOR.memUsed,
                      reading: seriesReading(seriesOf(metricMap.mysql_threads_connected), 'counts')
                    },
                    {
                      label: mysqlCategoryText(t, 'activeSessions'),
                      color: HOST_SERIES_COLOR.load1,
                      reading: seriesReading(seriesOf(metricMap.mysql_threads_running), 'counts')
                    }
                  ]}
                />
              </div>
            ) : null}
            {showThroughput ? (
              <div id="mysql-perf-throughput" className={cardClass(connectionWide)}>
                <ThinTimeSeries
                  title={mysqlCategoryText(t, 'qpsTps')}
                  hint={mysqlCategoryText(t, 'qpsTpsHint')}
                  loading={throughputAwaiting}
                  unit="cps"
                  data={throughput}
                  emptyText={empty}
                  keepLegend
                  legends={[
                    {
                      label: mysqlCategoryText(t, 'qps'),
                      color: HOST_SERIES_COLOR.memAvailable,
                      reading: seriesReading(seriesOf(metricMap.mysql_queries_rate), 'cps')
                    },
                    {
                      label: mysqlCategoryText(t, 'tps'),
                      color: HOST_PALETTE.orange,
                      reading: seriesReading(tpsTotal, 'cps')
                    }
                  ]}
                />
              </div>
            ) : null}
            {showMaxUsed ? (
              <div id="mysql-perf-max-used" className={cardClass(connectionWide)}>
                <ThinTimeSeries
                  title={mysqlCategoryText(t, 'maxUsedConnections')}
                  hint={mysqlCategoryText(t, 'maxUsedConnectionsHint')}
                  unit="counts"
                  data={maxUsed.map((point) => ({ time: point.time, value1: point.value1 }))}
                  emptyText={empty}
                  legends={[{
                    label: mysqlCategoryText(t, 'maxUsedConnections'),
                    color: HOST_PALETTE.neutral,
                    reading: seriesReading(maxUsed, 'counts')
                  }]}
                />
              </div>
            ) : null}
          </div>
          ) : null}
          {showThreadsCreated ? (
            <div className={`${pro.perfGrid} ${pro.perfFill}`} data-perf-section="threads-created">
              <div className={cardClass(true)}>
                <ThinTimeSeries
                  title={mysqlCategoryText(t, 'threadsCreated')}
                  unit="cps"
                  data={threadsCreated.map((point) => ({ time: point.time, value1: point.value1 }))}
                  emptyText={empty}
                  legends={[{
                    label: mysqlCategoryText(t, 'threadsCreated'),
                    color: HOST_SERIES_COLOR.load5,
                    reading: rateReading(metricMap.mysql_threads_created_rate)
                  }]}
                />
              </div>
            </div>
          ) : null}
        </ProSection>
      ) : null}
      {showTps || showInnodbRows ? (
        <ProSection title={showTps ? mysqlCategoryText(t, 'tpsChart') : mysqlCategoryText(t, 'innodbRows')}>
          <div className={`${pro.perfGrid} ${pro.perfFill}`}>
            {showTps ? (
              <div id="mysql-perf-tps" className={cardClass(!showInnodbRows)}>
                <ThinTimeSeries
                  title={mysqlCategoryText(t, 'tpsChart')}
                  hint={mysqlCategoryText(t, 'tpsHint')}
                  loading={tpsAwaiting}
                  unit="cps"
                  data={tpsMix.length ? tpsMix : mergeChartSeries([{ key: 'tps', label: mysqlCategoryText(t, 'tps'), data: tpsTotal }])}
                  emptyText={empty}
                  keepLegend
                  legends={tpsMix.length ? [
                    { label: mysqlCategoryText(t, 'commit'), color: HOST_SERIES_COLOR.memAvailable, reading: rateReading(metricMap.mysql_com_commit_rate) },
                    { label: mysqlCategoryText(t, 'rollback'), color: HOST_PALETTE.rose, reading: rateReading(metricMap.mysql_com_rollback_rate) }
                  ] : [
                    { label: mysqlCategoryText(t, 'tps'), color: HOST_PALETTE.orange, reading: rateReading(metricMap.mysql_tps_rate) }
                  ]}
                />
              </div>
            ) : null}
            {showInnodbRows ? (
              <div id="mysql-perf-rows" className={cardClass(!showTps)}>
                <ThinTimeSeries
                  title={mysqlCategoryText(t, 'innodbRows')}
                  hint={mysqlCategoryText(t, 'innodbRowsHint')}
                  loading={innodbRowsAwaiting}
                  unit="cps"
                  data={innodbRows}
                  emptyText={empty}
                  legends={[
                    { label: mysqlCategoryText(t, 'rowsRead'), color: HOST_SERIES_COLOR.memUsed, reading: rateReading(metricMap.mysql_innodb_rows_read_rate) },
                    { label: mysqlCategoryText(t, 'rowsInserted'), color: HOST_PALETTE.orange, reading: rateReading(metricMap.mysql_innodb_rows_inserted_rate) },
                    { label: mysqlCategoryText(t, 'rowsUpdated'), color: HOST_SERIES_COLOR.load5, reading: rateReading(metricMap.mysql_innodb_rows_updated_rate) },
                    { label: mysqlCategoryText(t, 'rowsDeleted'), color: HOST_PALETTE.rose, reading: rateReading(metricMap.mysql_innodb_rows_deleted_rate) }
                  ]}
                />
              </div>
            ) : null}
          </div>
        </ProSection>
      ) : null}
      {showWrites || showInnodb ? (
        <div
          className={writeInnodbPair ? pro.pairRowSide : pro.pairRow}
          data-perf-pair={writeInnodbPair ? 'side' : 'single'}
        >
          {showWrites ? (
            <ProSection className={pro.pairCol} title={mysqlCategoryText(t, 'writesAndStatements')}>
              <ThinTimeSeries
                className={writeInnodbPair ? pro.pairFill : undefined}
                title={mysqlCategoryText(t, 'writeStatements')}
                loading={writesAwaiting}
                unit="cps"
                data={statementMix}
                emptyText={empty}
                legends={[
                  { label: 'INSERT', color: HOST_PALETTE.orange, reading: rateReading(metricMap.mysql_com_insert_rate) },
                  { label: 'UPDATE', color: HOST_SERIES_COLOR.load5, reading: rateReading(metricMap.mysql_com_update_rate) },
                  { label: 'DELETE', color: HOST_PALETTE.rose, reading: rateReading(metricMap.mysql_com_delete_rate) }
                ]}
              />
            </ProSection>
          ) : null}
          {showInnodb ? (
            <ProSection id="mysql-perf-innodb" className={pro.pairCol} title={mysqlCategoryText(t, 'innodb')}>
              {innodbCard}
            </ProSection>
          ) : null}
        </div>
      ) : null}
      <ProSection title={mysqlCategoryText(t, 'bufferPool')}>
        <div className={`${pro.perfGrid} ${pro.perfFill}`} data-perf-count={bufferCount}>
          <div id="mysql-perf-buffer" className={cardClass(bufferCount === 1)}>
            <ThinTimeSeries
              title={mysqlCategoryText(t, 'bufferHit')}
              hint={mysqlCategoryText(t, 'bufferHitHint')}
              loading={bufferAwaiting}
              unit="percent"
              data={buffer}
              emptyText={empty}
              legends={[{ label: mysqlCategoryText(t, 'hitRate'), color: HOST_SERIES_COLOR.cpu }]}
            />
          </div>
          {showDirty ? (
            <div id="mysql-perf-dirty" className="min-w-0">
              <ThinTimeSeries
                title={mysqlCategoryText(t, 'dirtyRatio')}
                hint={mysqlCategoryText(t, 'dirtyRatioHint')}
                loading={dirtyAwaiting}
                unit="percent"
                data={dirty.map((point) => ({ time: point.time, value1: point.value1 }))}
                emptyText={empty}
                legends={[{
                  label: mysqlCategoryText(t, 'dirtyRatio'),
                  color: HOST_PALETTE.amber,
                  reading: percentReading(metricMap.mysql_buffer_pool_dirty_ratio)
                }]}
              />
            </div>
          ) : null}
          {showDirtyPages ? (
            <div id="mysql-perf-dirty-pages" className="min-w-0">
              <ThinTimeSeries
                title={mysqlCategoryText(t, 'dirtyPages')}
                hint={mysqlCategoryText(t, 'dirtyPagesHint')}
                loading={dirtyPagesAwaiting}
                unit="counts"
                data={dirtyPages.map((point) => ({ time: point.time, value1: point.value1 }))}
                emptyText={empty}
                legends={[{
                  label: mysqlCategoryText(t, 'dirtyPages'),
                  color: HOST_PALETTE.amber,
                  reading: seriesReading(dirtyPages, 'counts')
                }]}
              />
            </div>
          ) : null}
          {showDataFsyncs ? (
            <div id="mysql-perf-data-fsyncs" className="min-w-0">
              <ThinTimeSeries
                title={mysqlCategoryText(t, 'dataFsyncs')}
                hint={mysqlCategoryText(t, 'dataFsyncsHint')}
                loading={dataFsyncsAwaiting}
                unit="cps"
                data={dataFsyncs.map((point) => ({ time: point.time, value1: point.value1 }))}
                emptyText={empty}
                legends={[{
                  label: mysqlCategoryText(t, 'dataFsyncs'),
                  color: HOST_SERIES_COLOR.diskWrite,
                  reading: rateReading(metricMap.mysql_innodb_data_fsyncs_rate)
                }]}
              />
            </div>
          ) : null}
        </div>
      </ProSection>
      {abortedConnects.length > 0 || abortedClients.length > 0 ? (
        <ProSection id="mysql-perf-quality" title={mysqlCategoryText(t, 'connectionQuality')}>
          <div className={`${pro.perfGrid} ${pro.perfFill}`} data-perf-section="quality">
            {abortedConnects.length > 0 ? (
              <div className={cardClass(abortedClients.length === 0)}>
                <ThinTimeSeries
                  title={mysqlCategoryText(t, 'abortedConnects')}
                  hint={mysqlCategoryText(t, 'abortedConnectsHint')}
                  unit="cps"
                  data={abortedConnects.map((point) => ({ time: point.time, value1: point.value1 }))}
                  emptyText={empty}
                  legends={[{ label: mysqlCategoryText(t, 'abortedConnects'), color: HOST_PALETTE.rose }]}
                />
              </div>
            ) : null}
            {abortedClients.length > 0 ? (
              <div className={cardClass(abortedConnects.length === 0)}>
                <ThinTimeSeries
                  title={mysqlCategoryText(t, 'abortedClients')}
                  hint={mysqlCategoryText(t, 'abortedClientsHint')}
                  unit="cps"
                  data={abortedClients.map((point) => ({ time: point.time, value1: point.value1 }))}
                  emptyText={empty}
                  legends={[{ label: mysqlCategoryText(t, 'abortedClients'), color: HOST_PALETTE.orange }]}
                />
              </div>
            ) : null}
          </div>
        </ProSection>
      ) : null}
      <ProSection id="mysql-perf-scan-lock" title={mysqlCategoryText(t, 'scanAndLock')}>
          <div className={`${pro.perfGrid} ${pro.perfFill}`} data-perf-section="scan-lock" data-perf-count={scanLockCount}>
            <div id="mysql-perf-lock-wait" className="min-w-0">
              <ThinTimeSeries
                title={mysqlCategoryText(t, 'lockWaitSessions')}
                hint={mysqlCategoryText(t, 'lockWaitSessionsHint')}
                loading={lockWaitAwaiting}
                unit="counts"
                data={lockWaitThreads.map((point) => ({ time: point.time, value1: point.value1 }))}
                emptyText={empty}
                legends={[{
                  label: mysqlCategoryText(t, 'lockWaitSessions'),
                  color: HOST_PALETTE.orange,
                  reading: seriesReading(lockWaitThreads, 'counts')
                }]}
              />
            </div>
            <div id="mysql-perf-tmp-disk" className="min-w-0">
              <ThinTimeSeries
                title={mysqlCategoryText(t, 'tmpDiskRatio')}
                hint={mysqlCategoryText(t, 'tmpDiskRatioHint')}
                loading={tmpDiskAwaiting}
                unit="percent"
                data={tmpDisk.map((point) => ({ time: point.time, value1: point.value1 }))}
                emptyText={empty}
                legends={[{
                  label: mysqlCategoryText(t, 'tmpDiskRatio'),
                  color: HOST_SERIES_COLOR.load5,
                  reading: percentReading(metricMap.mysql_tmp_disk_table_ratio)
                }]}
              />
            </div>
            <div id="mysql-perf-table-lock" className="min-w-0">
              <ThinTimeSeries
                title={mysqlCategoryText(t, 'tableLockWaits')}
                hint={mysqlCategoryText(t, 'tableLockWaitsHint')}
                loading={tableLockAwaiting}
                unit="cps"
                data={tableLockWaits.map((point) => ({ time: point.time, value1: point.value1 }))}
                emptyText={empty}
                legends={[{
                  label: mysqlCategoryText(t, 'tableLockWaits'),
                  color: HOST_PALETTE.amber,
                  reading: rateReading(metricMap.mysql_table_locks_waited_rate)
                }]}
              />
            </div>
            {showLogWaits ? (
              <div id="mysql-perf-log-waits" className="min-w-0">
                <ThinTimeSeries
                  title={mysqlCategoryText(t, 'logWaits')}
                  hint={mysqlCategoryText(t, 'logWaitsHint')}
                  loading={logWaitsAwaiting}
                  unit="cps"
                  data={logWaits.map((point) => ({ time: point.time, value1: point.value1 }))}
                  emptyText={empty}
                  legends={[{
                    label: mysqlCategoryText(t, 'logWaits'),
                    color: HOST_PALETTE.orange,
                    reading: rateReading(metricMap.mysql_innodb_log_waits_rate)
                  }]}
                />
              </div>
            ) : null}
          </div>
          {mergedScanLockCount > 0 ? (
            <div
              className={`${pro.perfGrid} ${pro.perfFill}`}
              data-perf-section="scan-lock-merged"
              data-perf-count={mergedScanLockCount}
            >
              {showScan ? (
                <div className={cardClass(mergedScanLockCount === 1)}>
                  <ThinTimeSeries
                    title={mysqlCategoryText(t, 'scan')}
                    hint={mysqlCategoryText(t, 'scanHint')}
                    loading={scanAwaiting}
                    unit="cps"
                    data={scanSeries}
                    emptyText={empty}
                    keepLegend
                    legends={[
                      {
                        label: mysqlCategoryText(t, 'kpiSlow'),
                        color: HOST_SERIES_COLOR.load1,
                        reading: rateReading(metricMap.mysql_slow_queries_rate)
                      },
                      {
                        label: mysqlCategoryText(t, 'selectScan'),
                        color: HOST_SERIES_COLOR.memAvailable,
                        reading: rateReading(metricMap.mysql_select_scan_rate)
                      }
                    ]}
                  />
                </div>
              ) : null}
              {showLocks ? (
                <div className={cardClass(mergedScanLockCount === 1)}>
                  <ThinTimeSeries
                    title={mysqlCategoryText(t, 'locks')}
                    hint={mysqlCategoryText(t, 'locksHint')}
                    loading={locksAwaiting}
                    unit="cps"
                    data={lockSeries}
                    emptyText={empty}
                    keepLegend
                    legends={[
                      {
                        label: mysqlCategoryText(t, 'rowLockWaits'),
                        color: HOST_PALETTE.orange,
                        reading: rateReading(metricMap.mysql_innodb_row_lock_waits_rate)
                      },
                      {
                        label: mysqlCategoryText(t, 'deadlocks'),
                        color: HOST_PALETTE.rose,
                        reading: rateReading(metricMap.mysql_innodb_deadlocks_rate)
                      }
                    ]}
                  />
                </div>
              ) : null}
              {showRowLockTime ? (
                <div className={cardClass(mergedScanLockCount === 1)}>
                  <ThinTimeSeries
                    title={mysqlCategoryText(t, 'rowLockTime')}
                    hint={mysqlCategoryText(t, 'rowLockTimeHint')}
                    unit="ms"
                    data={rowLockTime.map((point) => ({ time: point.time, value1: point.value1 }))}
                    emptyText={empty}
                    legends={[{
                      label: mysqlCategoryText(t, 'rowLockTime'),
                      color: HOST_PALETTE.rose,
                      reading: durationReading(metricMap.mysql_innodb_row_lock_time_avg)
                    }]}
                  />
                </div>
              ) : null}
            </div>
          ) : null}
      </ProSection>
    </>
  );
}

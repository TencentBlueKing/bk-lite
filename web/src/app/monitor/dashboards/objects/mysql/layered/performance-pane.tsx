'use client';

import React, { useMemo } from 'react';
import type { ChartData } from '@/app/monitor/types';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import { mergeChartSeries } from '../../../shared/utils/chart-data';
import type { MetricSeries } from '../types';
import { formatMetricValue } from '../../../shared/utils/format';
import { GrayTabEmptyState, ProSectionTitle, ThinTimeSeries } from '../../host/layered/pro-chrome';
import { HOST_PALETTE, HOST_SERIES_COLOR } from '../../host/config';
import { latestNumber, numericValue, primaryChartSeries } from '../../host/layered/readings';
import { innodbHasLoad } from './ia';
import { mysqlCategoryText } from './mysql-copy';
import pro from './pro.module.scss';

interface PerformancePaneProps {
  metricMap: Record<string, MetricSeries | undefined>;
  pendingMetricNames: ReadonlySet<string>;
}

const seriesOf = (metric: MetricSeries | undefined) => primaryChartSeries(metric?.viewData);

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
  const value = latestNumber(metric);
  if (value == null) return undefined;
  const formatted = formatMetricValue(value, 'cps');
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
  const connection = useMemo(() => mergeChartSeries([
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
    commit: seriesOf(metricMap.mysql_com_commit_rate),
    rollback: seriesOf(metricMap.mysql_com_rollback_rate),
    total: seriesOf(metricMap.mysql_tps_rate)
  }), [
    metricMap.mysql_com_commit_rate?.viewData,
    metricMap.mysql_com_rollback_rate?.viewData,
    metricMap.mysql_tps_rate?.viewData
  ]);

  const tpsTotal = tpsParts.total.length
    ? tpsParts.total
    : sumSeries([tpsParts.commit, tpsParts.rollback]);

  const throughput = useMemo(() => mergeChartSeries([
    { key: 'qps', label: mysqlCategoryText(t, 'qps'), data: seriesOf(metricMap.mysql_queries_rate) },
    { key: 'tps', label: mysqlCategoryText(t, 'tps'), data: tpsTotal }
  ]), [metricMap.mysql_queries_rate?.viewData, t, tpsTotal]);

  const tpsMix = useMemo(() => mergeChartSeries([
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
  const deadlockAwaiting = slotLoading(['mysql_innodb_deadlocks_rate'], deadlocks);
  const slowAwaiting = slotLoading(['mysql_slow_queries_rate'], slowQueries);
  const empty = mysqlCategoryText(t, 'noCollectData');

  const innodbCard = innodbHasLoad(metricMap) || innodbAwaiting ? (
    <ThinTimeSeries
      className="h-full max-[720px]:h-auto"
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
        hint={innodb.length > 0 ? mysqlCategoryText(t, 'innodbQuietHint') : undefined}
      />
    </div>
  );

  const showConnections = connectionAwaiting || connection.length > 0;
  const showMaxUsed = maxUsed.length > 0;
  const showThreadsCreated = threadsCreated.length > 0;
  const connectionAuxCount = [showMaxUsed, showThreadsCreated].filter(Boolean).length;
  const showThroughput = throughputAwaiting || throughput.length > 0;
  const showTps = tpsAwaiting || tpsMix.length > 0 || tpsTotal.length > 0;
  const showWrites = writesAwaiting || statementMix.length > 0;
  const showInnodb = innodbAwaiting || innodb.length > 0;
  const showInnodbRows = innodbRowsAwaiting || innodbRows.length > 0;
  const showBuffer = bufferAwaiting || buffer.length > 0;
  const showDirty = dirtyAwaiting || dirty.length > 0;
  const showDeadlocks = deadlockAwaiting || deadlocks.length > 0;
  const showSlow = slowQueries.length > 0 || slowAwaiting;
  const showSelectScan = selectScan.length > 0;
  const showRowLockWaits = rowLockWaits.length > 0;
  const showRowLockTime = rowLockTime.length > 0;
  const scanLockCount = [showSlow, showSelectScan, showRowLockWaits, showRowLockTime, showDeadlocks].filter(Boolean).length;
  const cardClass = (wide: boolean) => (wide ? `min-w-0 ${pro.perfWide}` : 'min-w-0');
  const scanLockClass = cardClass(scanLockCount === 1);
  const writeInnodbPair = showWrites && showInnodb;
  const pairCol = writeInnodbPair
    ? 'grid h-full min-w-0 grid-rows-[auto_minmax(auto,1fr)] gap-3 max-[720px]:h-auto max-[720px]:grid-rows-[auto_auto]'
    : 'flex min-w-0 flex-col gap-3';
  const pairCard = writeInnodbPair ? 'h-full max-[720px]:h-auto' : undefined;

  return (
    <>
      {showConnections || showThroughput || connectionAuxCount > 0 ? (
        <>
          <ProSectionTitle>{mysqlCategoryText(t, 'connectionsAndThroughput')}</ProSectionTitle>
          {showConnections || showThroughput ? (
          <div className={pro.perfGrid}>
            {showConnections ? (
              <div id="mysql-perf-connections" className={cardClass(!showThroughput)}>
                <ThinTimeSeries
                  title={mysqlCategoryText(t, 'connectionsAndSessions')}
                  hint={mysqlCategoryText(t, 'connectionsHint')}
                  loading={connectionAwaiting}
                  unit="counts"
                  data={connection}
                  emptyText={empty}
                  legends={[
                    { label: mysqlCategoryText(t, 'currentConnections'), color: HOST_SERIES_COLOR.memUsed },
                    { label: mysqlCategoryText(t, 'activeSessions'), color: HOST_SERIES_COLOR.load1 }
                  ]}
                />
              </div>
            ) : null}
            {showThroughput ? (
              <div id="mysql-perf-throughput" className={cardClass(!showConnections)}>
                <ThinTimeSeries
                  title={mysqlCategoryText(t, 'qpsTps')}
                  hint={mysqlCategoryText(t, 'qpsTpsHint')}
                  loading={throughputAwaiting}
                  unit="cps"
                  data={throughput}
                  emptyText={empty}
                  legends={[
                    { label: mysqlCategoryText(t, 'qps'), color: HOST_SERIES_COLOR.memAvailable },
                    { label: mysqlCategoryText(t, 'tps'), color: HOST_PALETTE.orange }
                  ]}
                />
              </div>
            ) : null}
          </div>
          ) : null}
          {connectionAuxCount > 0 ? (
            <div
              className={showConnections || showThroughput ? `${pro.perfGrid} mt-3` : pro.perfGrid}
              data-perf-section="connection-aux"
            >
              {showMaxUsed ? (
                <div className={cardClass(connectionAuxCount === 1)}>
                  <ThinTimeSeries
                    title={mysqlCategoryText(t, 'maxUsedConnections')}
                    unit="counts"
                    data={maxUsed.map((point) => ({ time: point.time, value1: point.value1 }))}
                    emptyText={empty}
                    legends={[{
                      label: mysqlCategoryText(t, 'maxUsedConnections'),
                      color: HOST_PALETTE.neutral
                    }]}
                  />
                </div>
              ) : null}
              {showThreadsCreated ? (
                <div className={cardClass(connectionAuxCount === 1)}>
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
              ) : null}
            </div>
          ) : null}
        </>
      ) : null}
      {showTps || showInnodbRows ? (
        <>
          <ProSectionTitle>{showTps ? mysqlCategoryText(t, 'tpsChart') : mysqlCategoryText(t, 'innodbRows')}</ProSectionTitle>
          <div className={pro.perfGrid}>
            {showTps ? (
              <div id="mysql-perf-tps" className={cardClass(!showInnodbRows)}>
                <ThinTimeSeries
                  title={mysqlCategoryText(t, 'tpsChart')}
                  hint={mysqlCategoryText(t, 'tpsHint')}
                  loading={tpsAwaiting}
                  unit="cps"
                  data={tpsMix.length ? tpsMix : mergeChartSeries([{ key: 'tps', label: mysqlCategoryText(t, 'tps'), data: tpsTotal }])}
                  emptyText={empty}
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
        </>
      ) : null}
      {showWrites || showInnodb ? (
        <div
          className={writeInnodbPair
            ? 'grid grid-cols-2 items-stretch gap-3 max-[720px]:grid-cols-1'
            : 'grid grid-cols-1 gap-3'}
          data-perf-pair={writeInnodbPair ? 'side' : 'single'}
        >
          {showWrites ? (
            <div className={pairCol}>
              <ProSectionTitle>{mysqlCategoryText(t, 'writesAndStatements')}</ProSectionTitle>
              <ThinTimeSeries
                className={pairCard}
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
            </div>
          ) : null}
          {showInnodb ? (
            <div id="mysql-perf-innodb" className={pairCol}>
              <ProSectionTitle>{mysqlCategoryText(t, 'innodb')}</ProSectionTitle>
              {innodbCard}
            </div>
          ) : null}
        </div>
      ) : null}
      {showBuffer || showDirty ? (
        <>
          <ProSectionTitle>{mysqlCategoryText(t, 'bufferPool')}</ProSectionTitle>
          <div className={pro.perfGrid}>
            {showBuffer ? (
              <div id="mysql-perf-buffer" className={cardClass(!showDirty)}>
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
            ) : null}
            {showDirty ? (
              <div id="mysql-perf-dirty" className={cardClass(!showBuffer)}>
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
          </div>
        </>
      ) : null}
      {abortedConnects.length > 0 || abortedClients.length > 0 ? (
        <div id="mysql-perf-quality">
          <ProSectionTitle>{mysqlCategoryText(t, 'connectionQuality')}</ProSectionTitle>
          <div className={pro.perfGrid} data-perf-section="quality">
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
        </div>
      ) : null}
      {scanLockCount > 0 ? (
        <div id="mysql-perf-scan-lock">
          <ProSectionTitle>{mysqlCategoryText(t, 'scanAndLock')}</ProSectionTitle>
          <div className={pro.perfGrid} data-perf-section="scan-lock" data-perf-count={scanLockCount}>
            {showSlow ? (
              <div className={scanLockClass}>
                <ThinTimeSeries
                  title={mysqlCategoryText(t, 'kpiSlow')}
                  hint={mysqlCategoryText(t, 'slowQueriesHint')}
                  loading={slowAwaiting}
                  unit="cps"
                  data={slowQueries.map((point) => ({ time: point.time, value1: point.value1 }))}
                  emptyText={empty}
                  legends={[{ label: mysqlCategoryText(t, 'kpiSlow'), color: HOST_SERIES_COLOR.load1 }]}
                />
              </div>
            ) : null}
            {showSelectScan ? (
              <div className={scanLockClass}>
                <ThinTimeSeries
                  title={mysqlCategoryText(t, 'selectScan')}
                  hint={mysqlCategoryText(t, 'selectScanHint')}
                  unit="cps"
                  data={selectScan.map((point) => ({ time: point.time, value1: point.value1 }))}
                  emptyText={empty}
                  legends={[{ label: mysqlCategoryText(t, 'selectScan'), color: HOST_SERIES_COLOR.memAvailable }]}
                />
              </div>
            ) : null}
            {showRowLockWaits ? (
              <div className={scanLockClass}>
                <ThinTimeSeries
                  title={mysqlCategoryText(t, 'rowLockWaits')}
                  hint={mysqlCategoryText(t, 'rowLockWaitsHint')}
                  unit="cps"
                  data={rowLockWaits.map((point) => ({ time: point.time, value1: point.value1 }))}
                  emptyText={empty}
                  legends={[{
                    label: mysqlCategoryText(t, 'rowLockWaits'),
                    color: HOST_PALETTE.orange,
                    reading: rateReading(metricMap.mysql_innodb_row_lock_waits_rate)
                  }]}
                />
              </div>
            ) : null}
            {showDeadlocks ? (
              <div className={scanLockClass}>
                <ThinTimeSeries
                  title={mysqlCategoryText(t, 'deadlocks')}
                  hint={mysqlCategoryText(t, 'deadlocksHint')}
                  loading={deadlockAwaiting}
                  unit="cps"
                  data={deadlocks.map((point) => ({ time: point.time, value1: point.value1 }))}
                  emptyText={empty}
                  legends={[{
                    label: mysqlCategoryText(t, 'deadlocks'),
                    color: HOST_PALETTE.rose,
                    reading: rateReading(metricMap.mysql_innodb_deadlocks_rate)
                  }]}
                />
              </div>
            ) : null}
            {showRowLockTime ? (
              <div className={scanLockClass}>
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
        </div>
      ) : null}
    </>
  );
}

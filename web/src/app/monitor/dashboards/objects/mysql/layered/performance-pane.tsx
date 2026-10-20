'use client';

import React, { useMemo } from 'react';
import type { ChartData } from '@/app/monitor/types';
import { mergeChartSeries } from '../../../shared/utils/chart-data';
import type { MetricSeries } from '../types';
import { formatMetricValue } from '../../../shared/utils/format';
import { ThinTimeSeries } from '../../host/layered/pro-chrome';
import { HOST_PALETTE, HOST_SERIES_COLOR } from '../../host/config';
import { latestNumber, numericValue, primaryChartSeries } from '../../host/layered/readings';
import { innodbHasLoad } from './ia';
import classic from '../../host/index.module.scss';
import host from '../../host/layered/layered.module.scss';
import pro from './pro.module.scss';

interface PerformancePaneProps {
  metricMap: Record<string, MetricSeries | undefined>;
  loading: boolean;
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

export default function PerformancePane({ metricMap, loading }: PerformancePaneProps) {
  const connection = useMemo(() => mergeChartSeries([
    { key: 'connected', label: '当前连接', data: seriesOf(metricMap.mysql_threads_connected) },
    { key: 'running', label: '活跃会话', data: seriesOf(metricMap.mysql_threads_running) }
  ]), [metricMap.mysql_threads_connected?.viewData, metricMap.mysql_threads_running?.viewData]);

  const writes = useMemo(() => ({
    insert: seriesOf(metricMap.mysql_com_insert_rate),
    update: seriesOf(metricMap.mysql_com_update_rate),
    delete: seriesOf(metricMap.mysql_com_delete_rate)
  }), [
    metricMap.mysql_com_insert_rate?.viewData,
    metricMap.mysql_com_update_rate?.viewData,
    metricMap.mysql_com_delete_rate?.viewData
  ]);

  const throughput = useMemo(() => mergeChartSeries([
    { key: 'qps', label: 'QPS', data: seriesOf(metricMap.mysql_queries_rate) },
    { key: 'tps', label: 'TPS', data: sumSeries([writes.insert, writes.update, writes.delete]) }
  ]), [metricMap.mysql_queries_rate?.viewData, writes]);

  const statementMix = useMemo(() => mergeChartSeries([
    { key: 'insert', label: 'INSERT', data: writes.insert },
    { key: 'update', label: 'UPDATE', data: writes.update },
    { key: 'delete', label: 'DELETE', data: writes.delete }
  ]), [writes]);

  const innodb = useMemo(() => mergeChartSeries([
    { key: 'read', label: '读', data: seriesOf(metricMap.mysql_innodb_data_reads_rate) },
    { key: 'write', label: '写', data: seriesOf(metricMap.mysql_innodb_data_writes_rate) },
    { key: 'redo', label: 'Redo 刷盘', data: seriesOf(metricMap.mysql_innodb_os_log_fsyncs_rate) }
  ]), [
    metricMap.mysql_innodb_data_reads_rate?.viewData,
    metricMap.mysql_innodb_data_writes_rate?.viewData,
    metricMap.mysql_innodb_os_log_fsyncs_rate?.viewData
  ]);

  const buffer = useMemo(() => mergeChartSeries([
    { key: 'hit', label: '命中率', data: seriesOf(metricMap.mysql_buffer_pool_hit_ratio) }
  ]), [metricMap.mysql_buffer_pool_hit_ratio?.viewData]);

  const replication = useMemo(() => mergeChartSeries([
    { key: 'delay', label: '复制延迟', data: seriesOf(metricMap.mysql_slave_seconds_behind_master) }
  ]), [metricMap.mysql_slave_seconds_behind_master?.viewData]);

  const innodbCard = innodbHasLoad(metricMap) ? (
    <ThinTimeSeries
      title="InnoDB 读写"
      hint="读、写与 Redo 刷盘。近窗接近零时不放大噪声。"
      loading={loading}
      unit="cps"
      data={innodb}
      legends={[
        { label: '读', color: HOST_SERIES_COLOR.diskRead, reading: rateReading(metricMap.mysql_innodb_data_reads_rate) },
        { label: '写', color: HOST_SERIES_COLOR.diskWrite, reading: rateReading(metricMap.mysql_innodb_data_writes_rate) },
        { label: 'Redo', color: HOST_SERIES_COLOR.load1, reading: rateReading(metricMap.mysql_innodb_os_log_fsyncs_rate) }
      ]}
    />
  ) : (
    <section className={`${classic.panel} ${host.chartPanel}`}>
      <div className={host.chartHead}>
        <div className={host.chartTitle}>InnoDB 读写</div>
      </div>
      <div className="flex h-[72px] flex-col items-center justify-center text-center">
        <div className="text-[13px] font-semibold text-[var(--color-text-2)]">
          {innodb.length > 0 ? '近窗无明显 InnoDB 读写' : '暂无采集数据'}
        </div>
        {innodb.length > 0 ? (
          <div className="mt-1 text-[12px] text-[var(--color-text-3)]">有负载时将显示读/写/Redo</div>
        ) : null}
      </div>
    </section>
  );

  return (
    <div className={pro.perfGrid}>
      <div id="mysql-perf-connections" className="min-w-0">
        <ThinTimeSeries
          title="连接与活跃会话"
          hint="当前连接数与 Threads_running。"
          loading={loading}
          unit="counts"
          data={connection}
          emptyText="暂无采集数据"
          legends={[
            { label: '当前连接', color: HOST_SERIES_COLOR.memUsed },
            { label: '活跃会话', color: HOST_SERIES_COLOR.load1 }
          ]}
        />
      </div>
      <div id="mysql-perf-throughput" className="min-w-0">
        <ThinTimeSeries
          title="QPS / TPS"
          hint="QPS 为实例 Queries/s。TPS 为 INSERT、UPDATE、DELETE 速率之和。"
          loading={loading}
          unit="cps"
          data={throughput}
          emptyText="暂无采集数据"
          legends={[
            { label: 'QPS', color: HOST_SERIES_COLOR.memAvailable },
            { label: 'TPS', color: HOST_PALETTE.orange }
          ]}
        />
      </div>
      <div className="min-w-0">
        <ThinTimeSeries
          title="写入语句"
          loading={loading}
          unit="cps"
          data={statementMix}
          emptyText="暂无采集数据"
          legends={[
            { label: 'INSERT', color: HOST_PALETTE.orange },
            { label: 'UPDATE', color: HOST_SERIES_COLOR.load5 },
            { label: 'DELETE', color: HOST_PALETTE.rose }
          ]}
        />
      </div>
      <div id="mysql-perf-innodb" className="min-w-0">
        {innodbCard}
      </div>
      <div id="mysql-perf-buffer" className={`min-w-0${replication.length > 0 ? '' : ` ${pro.perfWide}`}`}>
        <ThinTimeSeries
          title="缓冲池命中"
          hint="InnoDB buffer pool 命中率。"
          loading={loading}
          unit="percent"
          data={buffer}
          emptyText="暂无采集数据"
          legends={[{ label: '命中率', color: HOST_SERIES_COLOR.cpu }]}
        />
      </div>
      {replication.length > 0 ? (
        <div id="mysql-perf-replication" className="min-w-0">
          <ThinTimeSeries
            title="复制延迟"
            loading={loading}
            unit="s"
            data={replication}
            emptyText="暂无采集数据"
            legends={[{ label: '复制延迟', color: HOST_SERIES_COLOR.memUsed }]}
          />
        </div>
      ) : null}
    </div>
  );
}

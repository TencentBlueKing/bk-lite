'use client';

import React, { useMemo } from 'react';
import type { MetricSeries } from '../../common/simple-dashboard-core';
import { HOST_PALETTE } from '../config';
import { pointsToChartData, type EntityTableRow } from '../entity-series';
import LayeredEntityTable, { type LayeredColumn } from './entity-table';
import StatusCountRow, { processStatusItems } from './status-count';
import ThinTimeSeries from './thin-time-series';
import { formatPercent, formatUnit, latestNumber, percentTone } from './readings';
import classic from '../index.module.scss';
import styles from './layered.module.scss';

const numberOrNull = (value: number | null | undefined) => (
  value == null || !Number.isFinite(value) ? null : value
);

export default function FlatProcessSplit({
  rows,
  loading,
  selectedKey,
  onSelect,
  metrics,
  metricsLoading = false
}: {
  rows: EntityTableRow[];
  loading: boolean;
  selectedKey: string;
  onSelect: (key: string) => void;
  metrics?: Record<string, MetricSeries | undefined>;
  metricsLoading?: boolean;
}) {
  const sorted = useMemo(
    () => [...rows].sort((left, right) => (right.values.process_cpu_usage ?? -1) - (left.values.process_cpu_usage ?? -1)),
    [rows]
  );
  const selected = sorted.find((row) => row.key === selectedKey) || sorted[0];
  const name = selected?.labels.process_name || '';
  const cpu = numberOrNull(selected?.values.process_cpu_usage);
  const mem = numberOrNull(selected?.values.process_mem_usage);
  const columns = useMemo<LayeredColumn[]>(() => {
    const present = (key: string) => sorted.some((row) => numberOrNull(row.values[key]) != null);
    const next: LayeredColumn[] = [
      { key: 'process_name', title: '进程名', labelKey: 'process_name' }
    ];
    if (loading || present('process_cpu_usage')) next.push({ key: 'process_cpu_usage', title: 'CPU', unit: 'percent', emptyDash: true });
    if (loading || present('process_mem_usage')) next.push({ key: 'process_mem_usage', title: '内存', unit: 'percent', emptyDash: true });
    if (loading || present('process_memory_rss')) next.push({ key: 'process_memory_rss', title: 'RSS', unit: 'bytes', emptyDash: true });
    if (loading || present('process_num_threads')) next.push({ key: 'process_num_threads', title: '线程', unit: 'counts', emptyDash: true });
    if (loading || present('process_num_fds')) next.push({ key: 'process_num_fds', title: '句柄', unit: 'counts', emptyDash: true });
    if (loading || present('process_alive')) {
      next.push({
        key: 'process_alive',
        title: '存活',
        render: (row) => {
          const value = numberOrNull(row.values.process_alive);
          if (value == null) return '—';
          return value >= 1 ? '是' : '否';
        }
      });
    }
    return next;
  }, [loading, sorted]);

  const statusCounts = processStatusItems(
    latestNumber(metrics?.processes_blocked),
    latestNumber(metrics?.processes_zombies),
    metricsLoading
  );

  return (
    <>
      <StatusCountRow items={statusCounts} />
      <div className={styles.sectionHead}>
        <div className={classic.sectionLabel}>趋势</div>
        <div className={styles.hint}>点击下表行切换</div>
      </div>
      <div className={styles.processTop}>
        <ThinTimeSeries
          key={selected?.key || 'none'}
          title={name ? `CPU / 内存 · ${name}` : 'CPU / 内存'}
          reading={`${formatPercent(cpu)} / ${formatPercent(mem)}`}
          loading={loading}
          unit="percent"
          data={pointsToChartData([
            { points: selected?.series.process_cpu_usage || [] },
            { points: selected?.series.process_mem_usage || [] }
          ])}
          legends={[
            { label: 'CPU', color: HOST_PALETTE.emerald },
            { label: '内存', color: HOST_PALETTE.blue }
          ]}
        />
        <section className={`${classic.panel} ${styles.currentCard}`}>
          <div className={styles.currentKicker}>当前进程</div>
          <div className={styles.currentName}>{name || '—'}</div>
          <div className={styles.currentMetric}>
            CPU
            <b style={{ color: percentTone(cpu) }}>{formatPercent(cpu)}</b>
          </div>
          <div className={styles.currentMetric}>
            内存
            <b style={{ color: percentTone(mem) }}>{formatPercent(mem)}</b>
          </div>
          {numberOrNull(selected?.values.process_memory_rss) != null ? (
            <div className={styles.currentMetric}>
              RSS
              <b>{formatUnit(numberOrNull(selected?.values.process_memory_rss), 'bytes')}</b>
            </div>
          ) : null}
        </section>
      </div>

      <div className={styles.sectionHead}>
        <div className={classic.sectionLabel}>进程列表</div>
      </div>
      <LayeredEntityTable
        rows={sorted}
        columns={columns}
        loading={loading}
        selectedKey={selected?.key || ''}
        onSelect={onSelect}
        emptyText="暂无进程数据"
      />
    </>
  );
}

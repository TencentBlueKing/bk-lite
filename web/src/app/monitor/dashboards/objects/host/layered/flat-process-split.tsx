'use client';

import React, { useMemo } from 'react';
import { HOST_PALETTE } from '../config';
import { pointsToChartData, type EntityTableRow } from '../entity-series';
import LayeredEntityTable, { type LayeredColumn } from './entity-table';
import ThinTimeSeries from './thin-time-series';
import { formatPercent, formatUnit, percentTone } from './readings';
import classic from '../index.module.scss';
import styles from './layered.module.scss';

const numberOrNull = (value: number | null | undefined) => (
  value == null || !Number.isFinite(value) ? null : value
);

export default function FlatProcessSplit({
  rows,
  loading,
  selectedKey,
  onSelect
}: {
  rows: EntityTableRow[];
  loading: boolean;
  selectedKey: string;
  onSelect: (key: string) => void;
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
      { key: 'process_name', title: 'process_name', labelKey: 'process_name' }
    ];
    if (loading || present('process_cpu_usage')) next.push({ key: 'process_cpu_usage', title: 'cpu', unit: 'percent', emptyDash: true });
    if (loading || present('process_mem_usage')) next.push({ key: 'process_mem_usage', title: 'mem', unit: 'percent', emptyDash: true });
    if (loading || present('process_memory_rss')) next.push({ key: 'process_memory_rss', title: 'rss', unit: 'bytes', emptyDash: true });
    if (loading || present('process_num_threads')) next.push({ key: 'process_num_threads', title: 'threads', unit: 'counts', emptyDash: true });
    if (loading || present('process_num_fds')) next.push({ key: 'process_num_fds', title: 'fds', unit: 'counts', emptyDash: true });
    if (loading || present('process_alive')) {
      next.push({
        key: 'process_alive',
        title: 'alive',
        render: (row) => {
          const value = numberOrNull(row.values.process_alive);
          if (value == null) return '—';
          return value >= 1 ? '是' : '否';
        }
      });
    }
    return next;
  }, [loading, sorted]);

  return (
    <>
      <div className={styles.sectionHead}>
        <div className={classic.sectionLabel}>Metrics · 选中进程</div>
        <div className={styles.hint}>{`选中行驱动上图 · 默认 Top${name ? ` ${name}` : ''}`}</div>
      </div>
      <div className={styles.processTop}>
        <ThinTimeSeries
          key={selected?.key || 'none'}
          title={name ? `cpu / mem · ${name}` : 'cpu / mem'}
          reading={`${formatPercent(cpu)} / ${formatPercent(mem)}`}
          loading={loading}
          unit="percent"
          data={pointsToChartData([
            { points: selected?.series.process_cpu_usage || [] },
            { points: selected?.series.process_mem_usage || [] }
          ])}
          legends={[
            { label: 'cpu', color: HOST_PALETTE.emerald },
            { label: 'mem', color: HOST_PALETTE.blue }
          ]}
        />
        <section className={`${classic.panel} ${styles.currentCard}`}>
          <div className={styles.currentKicker}>当前</div>
          <div className={styles.currentName}>{name || '—'}</div>
          <div className={styles.currentMetric}>
            cpu
            <b style={{ color: percentTone(cpu) }}>{formatPercent(cpu)}</b>
          </div>
          <div className={styles.currentMetric}>
            mem
            <b style={{ color: percentTone(mem) }}>{formatPercent(mem)}</b>
          </div>
          {numberOrNull(selected?.values.process_memory_rss) != null ? (
            <div className={styles.currentMetric}>
              rss
              <b>{formatUnit(numberOrNull(selected?.values.process_memory_rss), 'bytes')}</b>
            </div>
          ) : null}
        </section>
      </div>

      <div className={styles.sectionHead}>
        <div className={classic.sectionLabel}>Top 进程</div>
      </div>
      <LayeredEntityTable
        rows={sorted}
        columns={columns}
        loading={loading}
        selectedKey={selected?.key || ''}
        onSelect={onSelect}
      />
      <div className={styles.footnote}>可采列：process_name / cpu / mem / rss / threads / fds / alive。无 PID / User / virt / 进程 IO。</div>
    </>
  );
}

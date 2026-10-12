'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { pointsToChartData, type EntityTableRow } from '../entity-series';
import LayeredEntityTable from './entity-table';
import ThinTimeSeries from './thin-time-series';
import styles from './layered.module.scss';

const PROCESS_COLUMNS = [
  { key: 'process_name', title: 'PROCESS', labelKey: 'process_name' },
  { key: 'process_cpu_usage', title: 'CPU%', unit: 'percent' as const, bar: true },
  { key: 'process_mem_usage', title: 'MEM%', unit: 'percent' as const, bar: true },
  { key: 'process_memory_rss', title: 'RSS', unit: 'bytes' as const },
  { key: 'process_num_threads', title: 'THREADS', unit: 'counts' as const },
  { key: 'process_num_fds', title: 'FDS', unit: 'counts' as const },
  { key: 'process_alive', title: '状态', unit: 'none' as const }
];

export default function FlatProcessSplit({
  rows,
  loading
}: {
  rows: EntityTableRow[];
  loading: boolean;
}) {
  const sorted = useMemo(
    () => [...rows].sort((left, right) => (right.values.process_cpu_usage ?? -1) - (left.values.process_cpu_usage ?? -1)),
    [rows]
  );
  const [selectedKey, setSelectedKey] = useState('');
  useEffect(() => {
    if (!sorted.length) {
      setSelectedKey('');
      return;
    }
    if (!sorted.some((row) => row.key === selectedKey)) setSelectedKey(sorted[0].key);
  }, [selectedKey, sorted]);
  const selected = sorted.find((row) => row.key === selectedKey) || sorted[0];
  const chartSeries = useMemo(() => {
    if (!selected) return [];
    return [
      { label: 'cpu', color: '#2dd4bf', points: selected.series.process_cpu_usage || [] },
      { label: 'mem', color: '#a78bfa', points: selected.series.process_mem_usage || [] }
    ].filter((item) => item.points.length);
  }, [selected]);
  const chartData = useMemo(
    () => pointsToChartData(chartSeries.map((item) => ({ points: item.points }))),
    [chartSeries]
  );
  const displayRows = useMemo(
    () =>
      sorted.map((row) => ({
        ...row,
        values: {
          ...row.values,
          process_alive: row.values.process_alive
        },
        labels: {
          ...row.labels,
          process_alive: row.values.process_alive === 1 ? '存活' : row.values.process_alive === 0 ? '失活' : '--'
        }
      })),
    [sorted]
  );
  const columns = PROCESS_COLUMNS.map((column) =>
    column.key === 'process_alive' ? { ...column, labelKey: 'process_alive' } : column
  );

  return (
    <div className={styles.processSplit}>
      <LayeredEntityTable
        rows={displayRows}
        columns={columns}
        loading={loading}
        selectedKey={selectedKey}
        onSelect={setSelectedKey}
      />
      <ThinTimeSeries
        title={selected ? `选中 ${selected.labels.process_name || ''}` : '选中进程'}
        data={chartData}
        legends={chartSeries.map((item) => ({ label: item.label, color: item.color }))}
        unit="percent"
        loading={loading}
      />
    </div>
  );
}

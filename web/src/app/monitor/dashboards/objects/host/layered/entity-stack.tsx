'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { pointsToChartData, type EntityTableRow } from '../entity-series';
import type { MetricUnit } from '../../../shared/types';
import LayeredEntityTable, { type LayeredColumn } from './entity-table';
import ThinTimeSeries from './thin-time-series';
import styles from './layered.module.scss';

export interface LayeredChartMetric {
  key: string;
  label: string;
  unit: MetricUnit;
  color: string;
}

const selectedLabel = (row: EntityTableRow | undefined) => {
  if (!row) return '';
  return [
    row.labels.path,
    row.labels.mount,
    row.labels.device,
    row.labels.name,
    row.labels.interface,
    row.labels.index,
    row.labels.process_name
  ]
    .filter(Boolean)
    .filter((value, index, list) => list.indexOf(value) === index)
    .join(' · ');
};

export default function LayeredEntityStack({
  rows,
  columns,
  chartMetrics,
  loading,
  errorText
}: {
  rows: EntityTableRow[];
  columns: LayeredColumn[];
  chartMetrics: LayeredChartMetric[];
  loading: boolean;
  errorText?: string;
}) {
  const [selectedKey, setSelectedKey] = useState('');
  useEffect(() => {
    if (!rows.length) {
      setSelectedKey('');
      return;
    }
    if (!rows.some((row) => row.key === selectedKey)) setSelectedKey(rows[0].key);
  }, [rows, selectedKey]);

  const selected = rows.find((row) => row.key === selectedKey) || rows[0];
  const groups = useMemo(() => {
    if (!selected) return [];
    const byUnit = new Map<MetricUnit, LayeredChartMetric[]>();
    chartMetrics.forEach((metric) => {
      if (!(selected.series[metric.key] || []).length) return;
      const list = byUnit.get(metric.unit) || [];
      list.push(metric);
      byUnit.set(metric.unit, list);
    });
    return Array.from(byUnit.entries());
  }, [chartMetrics, selected]);
  const title = selectedLabel(selected);

  return (
    <div className={styles.entityStack}>
      {errorText ? <div className={styles.note}>{errorText}</div> : null}
      <LayeredEntityTable
        rows={rows}
        columns={columns}
        loading={loading}
        selectedKey={selectedKey}
        onSelect={setSelectedKey}
      />
      {groups.length ? (
        groups.map(([unit, metrics]) => (
          <ThinTimeSeries
            key={unit}
            title={title ? `选中 ${title}` : '选中行时序'}
            data={pointsToChartData(
              metrics.map((metric) => ({ points: selected?.series[metric.key] || [] }))
            )}
            legends={metrics.map((metric) => ({ label: metric.label, color: metric.color }))}
            unit={unit}
            loading={loading}
          />
        ))
      ) : (
        <ThinTimeSeries
          title={title ? `选中 ${title}` : '选中行时序'}
          data={[]}
          legends={[]}
          loading={loading}
        />
      )}
    </div>
  );
}

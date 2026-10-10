'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { TrendChartPanel } from '../../shared/widgets';
import { formatMetricValue } from '../../shared/utils/format';
import type { MetricUnit } from '../../shared/types';
import type { MetricItem } from '@/app/monitor/types';
import type { DashboardStyles } from '../common/dashboard-components';
import {
  pointsToChartData,
  type EntityTableRow,
  type RangePoint
} from './entity-series';

export interface EntityColumn {
  key: string;
  title: string;
  labelKey?: string;
  unit?: MetricUnit;
}

export interface EntityChartMetric {
  key: string;
  label: string;
  unit: MetricUnit;
  color: string;
}

interface HostEntityLayerProps {
  rows: EntityTableRow[];
  columns: EntityColumn[];
  chartMetrics: EntityChartMetric[];
  loading: boolean;
  errorText?: string;
  styles: DashboardStyles;
  onXRangeChange?: (range: [import('dayjs').Dayjs, import('dayjs').Dayjs]) => void;
}

const toneForPercent = (value: number) => {
  if (value >= 90) return 'var(--color-error)';
  if (value >= 80) return 'var(--color-warning)';
  return 'var(--color-text-1)';
};

const formatCell = (value: number | null | undefined, unit?: MetricUnit) => {
  if (value == null || !Number.isFinite(value)) return '--';
  if (!unit) return String(value);
  const formatted = formatMetricValue(value, unit);
  return `${formatted.value}${formatted.unit || ''}`;
};

const chartMetricItem = (title: string, unit: string): MetricItem => ({
  id: 0,
  metric_group: 0,
  metric_object: 0,
  name: title,
  type: 'number',
  display_name: title,
  dimensions: [],
  unit
});

export default function HostEntityLayer({
  rows,
  columns,
  chartMetrics,
  loading,
  errorText,
  styles,
  onXRangeChange
}: HostEntityLayerProps) {
  const [selectedKey, setSelectedKey] = useState('');

  useEffect(() => {
    if (!rows.length) {
      setSelectedKey('');
      return;
    }
    if (!rows.some((row) => row.key === selectedKey)) {
      setSelectedKey(rows[0].key);
    }
  }, [rows, selectedKey]);

  const selected = rows.find((row) => row.key === selectedKey) || rows[0];
  const chartSeries = useMemo(() => {
    if (!selected) return [];
    return chartMetrics
      .map((metric) => ({
        metric,
        points: (selected.series[metric.key] || []) as RangePoint[]
      }))
      .filter((item) => item.points.length > 0);
  }, [chartMetrics, selected]);

  const chartData = useMemo(
    () => pointsToChartData(chartSeries.map((item) => ({ points: item.points }))),
    [chartSeries]
  );
  const chartUnit = (chartSeries[0]?.metric.unit || 'none') as MetricUnit;
  const selectedLabel = selected
    ? [selected.labels.path, selected.labels.mount, selected.labels.device, selected.labels.name, selected.labels.interface, selected.labels.index]
      .filter(Boolean)
      .filter((value, index, list) => list.indexOf(value) === index)
      .join(' · ')
    : '';

  const tableColumns: ColumnsType<EntityTableRow> = columns.map((column) => ({
    title: column.title,
    key: column.key,
    ellipsis: true,
    render: (_, row) => {
      if (column.labelKey) {
        return row.labels[column.labelKey] || '--';
      }
      const value = row.values[column.key];
      const text = formatCell(value, column.unit);
      const color = column.unit === 'percent' && value != null ? toneForPercent(value) : undefined;
      return <span style={color ? { color } : undefined}>{text}</span>;
    }
  }));

  return (
    <div className={styles.entitySplit}>
      <div className={`${styles.panel} ${styles.entityTable}`}>
        {errorText ? <Alert className="mb-2" type="error" showIcon message={errorText} /> : null}
        <Table<EntityTableRow>
          size="small"
          rowKey="key"
          loading={loading}
          columns={tableColumns}
          dataSource={rows}
          pagination={false}
          scroll={{ x: 'max-content', y: 360 }}
          locale={{ emptyText: loading ? '加载中' : '当前时间窗没有维度序列' }}
          rowClassName={(row) => (row.key === selected?.key ? styles.entityRowActive : styles.entityRow)}
          onRow={(row) => ({
            onClick: () => setSelectedKey(row.key)
          })}
        />
      </div>
      <TrendChartPanel
        className={styles.entityChart}
        styles={styles}
        title={selectedLabel ? `选中 · ${selectedLabel}` : '选中行时序'}
        subtitle="与页面时间窗一致"
        legends={chartSeries.map((item) => ({
          label: item.metric.label,
          color: item.metric.color,
          primary: item.metric.key === chartSeries[0]?.metric.key
        }))}
        data={chartData}
        metric={chartMetricItem(selectedLabel || 'entity', chartUnit)}
        unit={chartUnit}
        loading={loading}
        seriesStyles={chartSeries.map((item) => ({
          color: item.metric.color,
          unit: item.metric.unit
        }))}
        onXRangeChange={onXRangeChange}
      />
    </div>
  );
}

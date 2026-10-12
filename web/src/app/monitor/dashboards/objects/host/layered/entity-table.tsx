'use client';

import React from 'react';
import { Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { formatMetricValue } from '../../../shared/utils/format';
import type { MetricUnit } from '../../../shared/types';
import type { EntityTableRow } from '../entity-series';
import styles from './layered.module.scss';

export interface LayeredColumn {
  key: string;
  title: string;
  labelKey?: string;
  unit?: MetricUnit;
  bar?: boolean;
}

const formatCell = (value: number | null | undefined, unit?: MetricUnit) => {
  if (value == null || !Number.isFinite(value)) return '--';
  if (!unit || unit === 'none') return String(value);
  const formatted = formatMetricValue(value, unit);
  return `${formatted.value}${formatted.unit || ''}`;
};

const toneForPercent = (value: number) => {
  if (value >= 90) return 'var(--l1-crit)';
  if (value >= 80) return 'var(--l1-warn)';
  return 'var(--l1-ok)';
};

export default function LayeredEntityTable({
  rows,
  columns,
  loading,
  selectedKey,
  onSelect
}: {
  rows: EntityTableRow[];
  columns: LayeredColumn[];
  loading: boolean;
  selectedKey: string;
  onSelect: (key: string) => void;
}) {
  const tableColumns: ColumnsType<EntityTableRow> = columns.map((column) => ({
    title: column.title,
    key: column.key,
    ellipsis: true,
    sorter: column.labelKey
      ? (left, right) => (left.labels[column.labelKey!] || '').localeCompare(right.labels[column.labelKey!] || '')
      : (left, right) => (left.values[column.key] ?? Number.NEGATIVE_INFINITY) - (right.values[column.key] ?? Number.NEGATIVE_INFINITY),
    render: (_, row) => {
      if (column.labelKey) return row.labels[column.labelKey] || '--';
      const value = row.values[column.key];
      const color = column.unit === 'percent' && value != null ? toneForPercent(value) : undefined;
      return (
        <span className={column.bar ? styles.quotaCell : undefined} style={color ? { color } : undefined}>
          {column.bar && value != null && Number.isFinite(value) ? (
            <span className={styles.miniBar} aria-hidden="true">
              <span
                className={styles.miniBarFill}
                style={{
                  width: `${Math.min(100, Math.max(0, value))}%`,
                  background: color || 'var(--l1-muted)'
                }}
              />
            </span>
          ) : null}
          {formatCell(value, column.unit)}
        </span>
      );
    }
  }));

  return (
    <div className={styles.tableWrap}>
      <Table<EntityTableRow>
        size="small"
        rowKey="key"
        loading={loading}
        pagination={false}
        columns={tableColumns}
        dataSource={rows}
        scroll={{ x: 'max-content', y: 280 }}
        locale={{ emptyText: loading ? '加载中' : '当前时间窗没有维度序列' }}
        rowClassName={(row) => (row.key === selectedKey ? styles.rowActive : styles.rowIdle)}
        onRow={(row) => ({ onClick: () => onSelect(row.key) })}
      />
    </div>
  );
}

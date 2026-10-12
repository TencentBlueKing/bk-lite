'use client';

import React from 'react';
import { Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { formatMetricValue } from '../../../shared/utils/format';
import type { MetricUnit } from '../../../shared/types';
import type { EntityTableRow } from '../entity-series';
import classic from '../index.module.scss';
import styles from './layered.module.scss';

export interface LayeredColumn {
  key: string;
  title: string;
  labelKey?: string;
  unit?: MetricUnit;
  bar?: boolean;
  /** 缺失值用「—」，表示没有这项采集或对不上，而不是 0。 */
  emptyDash?: boolean;
  render?: (row: EntityTableRow, index: number) => React.ReactNode;
}

const formatCell = (value: number | null | undefined, unit?: MetricUnit, emptyDash?: boolean) => {
  if (value == null || !Number.isFinite(value)) return emptyDash ? '—' : '--';
  if (!unit || unit === 'none') return String(value);
  const formatted = formatMetricValue(value, unit);
  return `${formatted.value}${formatted.unit || ''}`;
};

const toneForPercent = (value: number) => {
  if (value >= 90) return 'var(--color-fail)';
  if (value >= 80) return 'var(--color-warning)';
  return 'var(--color-success)';
};

export default function LayeredEntityTable({
  rows,
  columns,
  loading,
  selectedKey,
  onSelect,
  emptyText = '暂无数据'
}: {
  rows: EntityTableRow[];
  columns: LayeredColumn[];
  loading: boolean;
  selectedKey: string;
  onSelect: (key: string) => void;
  emptyText?: string;
}) {
  const tableColumns: ColumnsType<EntityTableRow> = columns.map((column) => ({
    title: column.title,
    key: column.key,
    ellipsis: true,
    sorter: column.labelKey
      ? (left, right) => (left.labels[column.labelKey!] || '').localeCompare(right.labels[column.labelKey!] || '')
      : column.render && !column.unit
        ? undefined
        : (left, right) => (left.values[column.key] ?? Number.NEGATIVE_INFINITY) - (right.values[column.key] ?? Number.NEGATIVE_INFINITY),
    render: (_, row, index) => {
      if (column.render) return column.render(row, index);
      if (column.labelKey) return row.labels[column.labelKey] || (column.emptyDash ? '—' : '--');
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
                  background: color || 'var(--color-text-3)'
                }}
              />
            </span>
          ) : null}
          {formatCell(value, column.unit, column.emptyDash)}
        </span>
      );
    }
  }));

  return (
    <div className={`${classic.panel} ${styles.tableWrap}`}>
      <Table<EntityTableRow>
        size="small"
        rowKey="key"
        loading={loading}
        pagination={false}
        columns={tableColumns}
        dataSource={rows}
        scroll={{ x: 'max-content', y: 280 }}
        locale={{ emptyText: loading ? '加载中' : emptyText }}
        rowClassName={(row) => (row.key === selectedKey ? styles.rowActive : styles.rowIdle)}
        onRow={(row) => ({ onClick: () => onSelect(row.key) })}
      />
    </div>
  );
}

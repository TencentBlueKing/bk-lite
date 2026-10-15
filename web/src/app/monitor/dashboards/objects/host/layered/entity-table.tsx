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
  /** 多行内容列关掉省略，避免 nowrap 把竖排路径挤成一行。 */
  ellipsis?: boolean;
  width?: number | string;
  align?: 'left' | 'right' | 'center';
  fixed?: 'left' | 'right';
  render?: (row: EntityTableRow, index: number) => React.ReactNode;
}

const USAGE_BAR_WARN = 80;
const USAGE_BAR_CRIT = 90;

/** 有限使用率才上色：<80 绿，80–90 黄，≥90 红。NaN / 空值不进这里，避免刷成 0% 绿。 */
const usageBarFillClass = (value: number) => {
  if (value >= USAGE_BAR_CRIT) return styles.miniBarFillError;
  if (value >= USAGE_BAR_WARN) return styles.miniBarFillWarning;
  return styles.miniBarFillSuccess;
};

const formatCell = (value: number | null | undefined, unit?: MetricUnit, emptyDash?: boolean) => {
  if (value == null || !Number.isFinite(value)) return emptyDash ? '—' : '--';
  if (!unit || unit === 'none') return String(value);
  const formatted = formatMetricValue(value, unit);
  return `${formatted.value}${formatted.unit || ''}`;
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
    width: column.width,
    align: column.align,
    fixed: column.fixed,
    ellipsis: column.ellipsis !== false,
    sorter: column.labelKey
      ? (left, right) => (left.labels[column.labelKey!] || '').localeCompare(right.labels[column.labelKey!] || '')
      : column.render && !column.unit
        ? undefined
        : (left, right) => (left.values[column.key] ?? Number.NEGATIVE_INFINITY) - (right.values[column.key] ?? Number.NEGATIVE_INFINITY),
    render: (_, row, index) => {
      if (column.render) return column.render(row, index);
      if (column.labelKey) return row.labels[column.labelKey] || (column.emptyDash ? '—' : '--');
      const value = row.values[column.key];
      return (
        <span className={column.bar ? styles.quotaCell : undefined}>
          {column.bar && value != null && Number.isFinite(value) ? (
            <span className={styles.miniBar} aria-hidden="true">
              <span
                className={`${styles.miniBarFill} ${usageBarFillClass(value)}`}
                style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
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
        loading={loading && rows.length === 0}
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

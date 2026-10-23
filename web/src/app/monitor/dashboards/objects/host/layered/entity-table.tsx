'use client';

import React from 'react';
import { Table } from 'antd';
import type { ColumnsType, TableProps } from 'antd/es/table';
import { formatMetricValue } from '../../../shared/utils/format';
import { hostThresholdColor } from '../config';
import type { MetricUnit } from '../../../shared/types';
import type { EntityTableRow } from '../entity-series';
import { CardAlertDot, cardAlertClass } from './card-alert';
import ProDashLoading from './pro-dash-loading';
import type { TabAlertLevel } from './tab-level';
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
  /** 自定义排序。有 render 且无 unit 时默认不排序，数值列要显式传入。 */
  sorter?: (left: EntityTableRow, right: EntityTableRow) => number;
  defaultSortOrder?: 'ascend' | 'descend';
  /** 传入后该列受控。主机表不传，仍走 Ant 自己的表头状态。 */
  sortOrder?: 'ascend' | 'descend' | null;
  /** 导出用的可读文本。缺省时跟 label / 单位格式化，不含色点和迷你条。 */
  csvValue?: (row: EntityTableRow) => string;
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

/** 与单元格展示一致的导出文本。自定义 render 若不是纯文本，请另给 csvValue。 */
export const layeredColumnText = (column: LayeredColumn, row: EntityTableRow) => {
  if (column.csvValue) return column.csvValue(row);
  if (column.labelKey) {
    const text = row.labels[column.labelKey];
    if (text) return text;
    return column.emptyDash ? '—' : '--';
  }
  return formatCell(row.values[column.key], column.unit, column.emptyDash);
};

export default function LayeredEntityTable({
  rows,
  columns,
  loading,
  selectedKey,
  onSelect,
  emptyText = '暂无数据',
  expandedRowRender,
  rowExpandable,
  toolbar,
  title,
  alertLevel,
  scrollY = 280,
  onChange
}: {
  rows: EntityTableRow[];
  columns: LayeredColumn[];
  loading: boolean;
  selectedKey: string;
  onSelect: (key: string) => void;
  emptyText?: React.ReactNode;
  /** 框内顶栏左侧标题。与 toolbar 同一行，不浮到表框外。 */
  title?: React.ReactNode;
  /** 选中行下方的附加行。未提供时表格不出现展开列。 */
  expandedRowRender?: (row: EntityTableRow) => React.ReactNode;
  rowExpandable?: (row: EntityTableRow) => boolean;
  /** 表框内、列头上方右侧。导出按钮放这里，不浮在边框外。 */
  toolbar?: React.ReactNode;
  /** 本表达档。不传或 none 时不打点、不加框。 */
  alertLevel?: TabAlertLevel;
  /**
   * 表体纵向滚动上限。false 时表体跟行数走，不预留空高，避免外层再滚过假空白。
   * 主机盘默认仍是 280。
   */
  scrollY?: number | false;
  onChange?: TableProps<EntityTableRow>['onChange'];
}) {
  const tableColumns: ColumnsType<EntityTableRow> = columns.map((column) => ({
    title: column.title,
    key: column.key,
    width: column.width,
    align: column.align,
    fixed: column.fixed,
    ellipsis: column.ellipsis !== false,
    defaultSortOrder: column.defaultSortOrder,
    ...(column.sortOrder !== undefined ? { sortOrder: column.sortOrder } : {}),
    sorter: column.sorter
      ? column.sorter
      : column.labelKey
        ? (left, right) => (left.labels[column.labelKey!] || '').localeCompare(right.labels[column.labelKey!] || '')
        : column.render && !column.unit
          ? undefined
          : (left, right) => (left.values[column.key] ?? Number.NEGATIVE_INFINITY) - (right.values[column.key] ?? Number.NEGATIVE_INFINITY),
    render: (_, row, index) => {
      if (column.render) return column.render(row, index);
      if (column.labelKey) return row.labels[column.labelKey] || (column.emptyDash ? '—' : '--');
      const value = row.values[column.key];
      const usageBar = column.bar && value != null && Number.isFinite(value);
      return (
        <span className={column.bar ? styles.quotaCell : undefined}>
          {usageBar ? (
            <span className={styles.miniBar} aria-hidden="true">
              <span
                className={`${styles.miniBarFill} ${usageBarFillClass(value)}`}
                style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
              />
            </span>
          ) : null}
          <span style={usageBar ? { color: hostThresholdColor(value), fontWeight: 600 } : undefined}>
            {formatCell(value, column.unit, column.emptyDash)}
          </span>
        </span>
      );
    }
  }));

  const expandable = expandedRowRender
    ? {
      showExpandColumn: false,
      expandedRowRender,
      rowExpandable,
      expandedRowKeys: rows
        .filter((row) => (rowExpandable ? rowExpandable(row) : true))
        .map((row) => row.key)
    }
    : undefined;

  return (
    <div
      className={`${classic.panel} ${styles.tableWrap} ${cardAlertClass(alertLevel)}`}
      aria-busy={loading && rows.length === 0 ? true : undefined}
    >
      <CardAlertDot level={alertLevel} />
      {title ? (
        <div className={`${styles.tableFrameHead}${alertLevel && alertLevel !== 'none' ? ` ${styles.cardAlertPad}` : ''}`}>
          <div className={styles.tableFrameTitle}>{title}</div>
          {toolbar ? <div className={styles.tableFrameTools}>{toolbar}</div> : null}
        </div>
      ) : toolbar ? (
        <div className={`mb-1 flex justify-end ${alertLevel && alertLevel !== 'none' ? styles.cardAlertPad : ''}`}>
          {toolbar}
        </div>
      ) : null}
      <Table<EntityTableRow>
        size="small"
        rowKey="key"
        loading={false}
        pagination={false}
        columns={tableColumns}
        dataSource={rows}
        scroll={scrollY === false ? { x: 'max-content' } : { x: 'max-content', y: scrollY }}
        locale={{
          emptyText: loading ? (
            <div className="flex min-h-[240px] items-center justify-center">
              <ProDashLoading />
            </div>
          ) : emptyText
        }}
        rowClassName={(row) => (row.key === selectedKey ? styles.rowActive : styles.rowIdle)}
        onRow={(row) => ({ onClick: () => onSelect(row.key) })}
        onChange={onChange}
        expandable={expandable}
      />
    </div>
  );
}

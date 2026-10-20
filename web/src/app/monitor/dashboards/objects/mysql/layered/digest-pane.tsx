'use client';

import React from 'react';
import { Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { mergeChartSeries } from '../../../shared/utils/chart-data';
import { GrayTabEmptyState, ThinTimeSeries } from '../../host/layered/pro-chrome';
import { HOST_SERIES_COLOR } from '../../host/config';
import host from '../../host/layered/layered.module.scss';
import {
  MYSQL_EMPTY_COPY,
  statementColumns,
  waitColumns,
  waitStatementTarget,
  type MysqlStatementRow,
  type MysqlWaitEventRow,
  type StatementColumn,
  type WaitColumn
} from './ia';
import pro from './pro.module.scss';

const formatOptional = (value: number | null | undefined, digits: number) => {
  if (value == null || !Number.isFinite(value)) return '';
  return Number(value.toFixed(digits)).toString();
};

const trendData = (points: Array<{ time: number; value: number }> | undefined) => (
  mergeChartSeries([{
    key: 'value',
    label: '趋势',
    data: (points || [])
      .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.value))
      .map((point) => ({ time: point.time, value1: point.value }))
  }])
);

const STATEMENT_TITLES: Record<StatementColumn, string> = {
  sql: '语句',
  totalTimeMs: '耗时 (ms)',
  calls: '次数',
  rowsExamined: '扫描行'
};

const WAIT_TITLES: Record<WaitColumn, string> = {
  name: '等待事件',
  waits: '次数',
  timeMs: '耗时 (ms)'
};

interface StatementPaneProps {
  rows: readonly MysqlStatementRow[];
  selectedId: string;
  onSelect: (id: string) => void;
  loading?: boolean;
}

export function StatementPane({ rows, selectedId, onSelect, loading = false }: StatementPaneProps) {
  if (loading && rows.length === 0) {
    return <GrayTabEmptyState title="加载中" />;
  }
  if (!rows.length) {
    return <GrayTabEmptyState {...MYSQL_EMPTY_COPY.statements} />;
  }
  const selected = rows.find((row) => row.id === selectedId) || rows[0];
  const columns = statementColumns(rows);
  const tableColumns: ColumnsType<MysqlStatementRow> = columns.map((key) => ({
    title: STATEMENT_TITLES[key],
    dataIndex: key,
    key,
    render: (value: unknown, row) => (
      key === 'sql'
        ? <span className={pro.sqlCell}>{row.sql}</span>
        : formatOptional(typeof value === 'number' ? value : null, key === 'calls' ? 0 : 1)
    )
  }));
  return (
    <div className={pro.chartStack}>
      <ThinTimeSeries
        title={selected.sql}
        unit={columns.includes('totalTimeMs') ? 'ms' : 'counts'}
        data={trendData(selected.trend)}
        legends={[{ label: '选中语句', color: HOST_SERIES_COLOR.memUsed }]}
        emptyText="该语句暂无趋势"
      />
      <div className={host.tableWrap}>
        <Table<MysqlStatementRow>
          size="small"
          pagination={false}
          rowKey="id"
          columns={tableColumns}
          dataSource={[...rows]}
          onRow={(row) => ({
            onClick: () => onSelect(row.id),
            className: row.id === selected.id ? host.rowActive : host.rowIdle
          })}
        />
      </div>
    </div>
  );
}

interface WaitPaneProps {
  rows: readonly MysqlWaitEventRow[];
  statements: readonly MysqlStatementRow[];
  selectedId: string;
  onSelect: (id: string) => void;
  onOpenStatement: (statementId: string) => void;
  loading?: boolean;
}

export function WaitPane({
  rows,
  statements,
  selectedId,
  onSelect,
  onOpenStatement,
  loading = false
}: WaitPaneProps) {
  if (loading && rows.length === 0) {
    return <GrayTabEmptyState title="加载中" />;
  }
  if (!rows.length) {
    return <GrayTabEmptyState {...MYSQL_EMPTY_COPY.waits} />;
  }
  const selected = rows.find((row) => row.id === selectedId) || rows[0];
  const columns = waitColumns(rows);
  const tableColumns: ColumnsType<MysqlWaitEventRow> = [
    ...columns.map((key) => ({
      title: WAIT_TITLES[key],
      dataIndex: key,
      key,
      render: (value: unknown, row: MysqlWaitEventRow) => (
        key === 'name'
          ? row.name
          : formatOptional(typeof value === 'number' ? value : null, key === 'waits' ? 0 : 1)
      )
    })),
    {
      title: '语句',
      key: 'statement',
      render: (_value, row) => {
        const target = waitStatementTarget(row, statements);
        if (!target) return null;
        return (
          <button
            type="button"
            className={host.jumpBtn}
            onClick={(event) => {
              event.stopPropagation();
              onOpenStatement(target);
            }}
          >
            查看语句
          </button>
        );
      }
    }
  ];
  return (
    <div className={pro.chartStack}>
      <ThinTimeSeries
        title={selected.name}
        unit="counts"
        data={trendData(selected.trend)}
        legends={[{ label: '等待', color: HOST_SERIES_COLOR.load1 }]}
        emptyText="该等待事件暂无趋势"
      />
      <div className={host.tableWrap}>
        <Table<MysqlWaitEventRow>
          size="small"
          pagination={false}
          rowKey="id"
          columns={tableColumns}
          dataSource={[...rows]}
          onRow={(row) => ({
            onClick: () => onSelect(row.id),
            className: row.id === selected.id ? host.rowActive : host.rowIdle
          })}
        />
      </div>
    </div>
  );
}

'use client';

import React from 'react';
import { Button } from 'antd';
import { mergeChartSeries } from '../../../shared/utils/chart-data';
import type { EntityTableRow } from '../../host/entity-series';
import LayeredEntityTable, { type LayeredColumn } from '../../host/layered/entity-table';
import TableCsvExportButton from '../../host/layered/table-csv-export';
import { ThinTimeSeries } from '../../host/layered/pro-chrome';
import { HOST_SERIES_COLOR } from '../../host/config';
import {
  MYSQL_EMPTY_COPY,
  formatAverageLatency,
  formatCallCount,
  formatTimeShare,
  primaryWaitForStatement,
  relatedStatementRows,
  statementColumns,
  waitColumns,
  type MysqlStatementRow,
  type MysqlWaitEventRow,
  type StatementColumn,
  type WaitColumn
} from './ia';
import pro from './pro.module.scss';

const STATEMENT_TITLES: Record<StatementColumn, string> = {
  sql: '语句',
  timeShare: '耗时占比',
  calls: '调用次数',
  avgSeconds: '平均耗时',
  rowsExamined: '扫描行'
};

const WAIT_TITLES: Record<WaitColumn, string> = {
  name: '等待事件',
  waits: '次数',
  timeMs: '耗时 (ms)'
};

const TEXT_BUTTON = '!h-auto shrink-0 !px-1 !text-[13px] !text-[var(--color-text-2)] hover:!text-[var(--color-primary)]';

const trendData = (points: Array<{ time: number; value: number }> | undefined) => (
  mergeChartSeries([{
    key: 'value',
    label: '趋势',
    data: (points || [])
      .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.value))
      .map((point) => ({ time: point.time, value1: point.value }))
  }])
);

const emptyCopy = (copy: { title: string; hint?: string }) => (
  <div className="px-3 py-2 text-center">
    <div className="text-[13px] font-semibold text-[var(--color-text-2)]">{copy.title}</div>
    {copy.hint ? <div className="mt-1 text-[12px] text-[var(--color-text-3)]">{copy.hint}</div> : null}
  </div>
);

const statementLabel = (key: StatementColumn, row: MysqlStatementRow) => {
  if (key === 'sql') return row.sql || '--';
  if (key === 'timeShare') return formatTimeShare(row.timeShare);
  if (key === 'calls') return formatCallCount(row.calls);
  if (key === 'avgSeconds') return formatAverageLatency(row.avgSeconds);
  return formatCallCount(row.rowsExamined);
};

const statementEntities = (rows: readonly MysqlStatementRow[]): EntityTableRow[] => (
  rows.map((row) => {
    const labels: Record<string, string> = {};
    statementColumns(rows).forEach((key) => {
      labels[key] = statementLabel(key, row);
    });
    return { key: row.id, labels, values: {}, series: {} };
  })
);

const statementLayerColumns = (rows: readonly MysqlStatementRow[]): LayeredColumn[] => (
  statementColumns(rows).map((key) => ({
    key,
    title: STATEMENT_TITLES[key],
    align: key === 'sql' ? 'left' : 'right',
    ellipsis: key !== 'sql',
    render: (entity) => (
      key === 'sql'
        ? <span className={pro.sqlCell}>{entity.labels.sql || '--'}</span>
        : (entity.labels[key] || '--')
    ),
    csvValue: (entity) => entity.labels[key] || '--'
  }))
);

const formatWaitMs = (value: number | null | undefined) => {
  if (value == null || !Number.isFinite(value)) return '--';
  return Number(value.toFixed(1)).toString();
};

const waitLabel = (key: WaitColumn, row: MysqlWaitEventRow) => {
  if (key === 'name') return row.name || '--';
  if (key === 'waits') return formatCallCount(row.waits);
  return formatWaitMs(row.timeMs);
};

const waitEntities = (rows: readonly MysqlWaitEventRow[]): EntityTableRow[] => (
  rows.map((row) => {
    const labels: Record<string, string> = {};
    waitColumns(rows).forEach((key) => {
      labels[key] = waitLabel(key, row);
    });
    return { key: row.id, labels, values: {}, series: {} };
  })
);

const waitLayerColumns = (rows: readonly MysqlWaitEventRow[]): LayeredColumn[] => (
  waitColumns(rows).map((key) => ({
    key,
    title: WAIT_TITLES[key],
    align: key === 'name' ? 'left' as const : 'right' as const,
    ellipsis: key !== 'name',
    render: (entity) => entity.labels[key] || '--',
    csvValue: (entity) => entity.labels[key] || '--'
  }))
);

const csvHost = (instanceName: string) => instanceName.trim() || 'mysql';

interface StatementPaneProps {
  rows: readonly MysqlStatementRow[];
  waits?: readonly MysqlWaitEventRow[];
  selectedId: string;
  onSelect: (id: string) => void;
  loading?: boolean;
  instanceName: string;
}

export function StatementPane({
  rows,
  waits = [],
  selectedId,
  onSelect,
  loading = false,
  instanceName
}: StatementPaneProps) {
  const selected = rows.find((row) => row.id === selectedId) || rows[0];
  const entities = statementEntities(rows);
  const columns = statementLayerColumns(rows);
  const primaryWait = selected ? primaryWaitForStatement(selected.id, waits) : null;
  return (
    <div className={pro.chartStack}>
      {selected ? (
        <ThinTimeSeries
          title={selected.sql}
          unit={rows.some((row) => row.totalTimeMs != null) ? 'ms' : 'counts'}
          data={trendData(selected.trend)}
          legends={[{ label: '选中语句', color: HOST_SERIES_COLOR.memUsed }]}
          emptyText="该语句暂无趋势"
        />
      ) : null}
      {primaryWait ? (
        <div className="text-[12px] text-[var(--color-text-3)]">{`主要等待 ${primaryWait}`}</div>
      ) : null}
      <LayeredEntityTable
        title="语句列表"
        rows={entities}
        columns={columns}
        loading={loading}
        selectedKey={selected?.id || ''}
        onSelect={onSelect}
        emptyText={emptyCopy(MYSQL_EMPTY_COPY.statements)}
        toolbar={(
          <TableCsvExportButton
            host={csvHost(instanceName)}
            slug="statements"
            columns={columns}
            rows={entities}
          />
        )}
      />
    </div>
  );
}

interface WaitPaneProps {
  rows: readonly MysqlWaitEventRow[];
  statements: readonly MysqlStatementRow[];
  selectedId: string;
  onSelect: (id: string) => void;
  loading?: boolean;
  instanceName: string;
  statementsCollected: boolean;
}

export function WaitPane({
  rows,
  statements,
  selectedId,
  onSelect,
  loading = false,
  instanceName,
  statementsCollected
}: WaitPaneProps) {
  const selected = rows.find((row) => row.id === selectedId) || null;
  const related = relatedStatementRows(selected, statements);
  const relatedRows = related ?? [];
  const waitTableRows = waitEntities(rows);
  const waitTableColumns = waitLayerColumns(rows);
  const relatedTableRows = statementEntities(relatedRows);
  const relatedTableColumns = statementLayerColumns(relatedRows);
  const host = csvHost(instanceName);
  const relatedEmpty = selected
    ? emptyCopy({
      title: '暂无与该等待关联的语句',
      hint: statementsCollected ? undefined : '需已开启语句采集'
    })
    : emptyCopy(MYSQL_EMPTY_COPY.statements);
  return (
    <div className={pro.chartStack}>
      {selected ? (
        <ThinTimeSeries
          title={selected.name}
          unit="counts"
          data={trendData(selected.trend)}
          legends={[{ label: '等待', color: HOST_SERIES_COLOR.load1 }]}
          emptyText="该等待事件暂无趋势"
        />
      ) : null}
      <div className={pro.perfGrid}>
        <LayeredEntityTable
          title="等待列表"
          rows={waitTableRows}
          columns={waitTableColumns}
          loading={loading}
          selectedKey={selected?.id || ''}
          onSelect={(key) => onSelect(key === selectedId ? '' : key)}
          emptyText={emptyCopy(MYSQL_EMPTY_COPY.waits)}
          toolbar={(
            <>
              {selected ? (
                <Button type="text" size="small" className={TEXT_BUTTON} onClick={() => onSelect('')}>
                  清除
                </Button>
              ) : null}
              <TableCsvExportButton
                host={host}
                slug="waits"
                columns={waitTableColumns}
                rows={waitTableRows}
              />
            </>
          )}
        />
        <LayeredEntityTable
          title="相关语句"
          rows={relatedTableRows}
          columns={relatedTableColumns}
          loading={loading && statements.length === 0 && rows.length === 0}
          selectedKey=""
          onSelect={() => undefined}
          emptyText={relatedEmpty}
          toolbar={(
            <TableCsvExportButton
              host={host}
              slug="wait_statements"
              columns={relatedTableColumns}
              rows={relatedTableRows}
            />
          )}
        />
      </div>
    </div>
  );
}

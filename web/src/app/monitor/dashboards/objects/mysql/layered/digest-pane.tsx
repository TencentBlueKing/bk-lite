'use client';

import React, { useState } from 'react';
import { Input } from 'antd';
import { mergeChartSeries } from '../../../shared/utils/chart-data';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import type { EntityTableRow } from '../../host/entity-series';
import LayeredEntityTable, { type LayeredColumn } from '../../host/layered/entity-table';
import TableCsvExportButton from '../../host/layered/table-csv-export';
import { GrayTabEmptyState, ProDashLoading, ProSectionTitle, ThinTimeSeries } from '../../host/layered/pro-chrome';
import host from '../../host/layered/layered.module.scss';
import { HOST_SERIES_COLOR } from '../../host/config';
import {
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
import { mysqlCategoryText, type MysqlCategoryCopyKey } from './mysql-copy';
import pro from './pro.module.scss';

const STATEMENT_TITLE_KEYS: Record<StatementColumn, MysqlCategoryCopyKey> = {
  sql: 'columnSql',
  timeShare: 'columnTimeShare',
  calls: 'columnCalls',
  avgSeconds: 'columnAvg',
  rowsExamined: 'columnRows'
};

const WAIT_TITLE_KEYS: Record<WaitColumn, MysqlCategoryCopyKey> = {
  name: 'columnWaitName',
  waits: 'columnWaitCount',
  timeMs: 'columnWaitTime'
};

const trendData = (points: Array<{ time: number; value: number }> | undefined, label: string) => (
  mergeChartSeries([{
    key: 'value',
    label,
    data: (points || [])
      .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.value))
      .map((point) => ({ time: point.time, value1: point.value }))
  }])
);

/** 表内空态按文案高度走。不要套趋势卡的 min-height，否则表底被撑出一块空白。 */
const emptyCopy = (copy: {
  title: string;
  hint?: string;
  actionLabel?: string;
  onAction?: () => void;
}) => (
  <div className="px-3 py-4 text-center">
    <div className="text-[13px] font-semibold text-[var(--color-text-2)]">{copy.title}</div>
    {copy.hint ? <div className="mt-1 text-[12px] text-[var(--color-text-3)]">{copy.hint}</div> : null}
    {copy.actionLabel && copy.onAction ? (
      <button type="button" className={host.emptyAction} onClick={copy.onAction}>
        {copy.actionLabel}
      </button>
    ) : null}
  </div>
);

const statementLabel = (key: StatementColumn, row: MysqlStatementRow) => {
  if (key === 'sql') return row.sql || '--';
  if (key === 'timeShare') return formatTimeShare(row.timeShare);
  if (key === 'calls') return formatCallCount(row.calls);
  if (key === 'avgSeconds') return formatAverageLatency(row.avgSeconds);
  return formatCallCount(row.rowsExamined);
};

const compareNumber = (left: number | null | undefined, right: number | null | undefined) => {
  const a = left == null || !Number.isFinite(left) ? Number.NEGATIVE_INFINITY : left;
  const b = right == null || !Number.isFinite(right) ? Number.NEGATIVE_INFINITY : right;
  return a - b;
};

const statementEntities = (rows: readonly MysqlStatementRow[]): EntityTableRow[] => (
  rows.map((row) => {
    const labels: Record<string, string> = {};
    (['sql', 'timeShare', 'calls', 'avgSeconds', 'rowsExamined'] as const).forEach((key) => {
      labels[key] = statementLabel(key, row);
    });
    return {
      key: row.id,
      labels,
      values: {
        timeShare: row.timeShare ?? null,
        calls: row.calls ?? null,
        avgSeconds: row.avgSeconds ?? null,
        rowsExamined: row.rowsExamined ?? null
      },
      series: {}
    };
  })
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
    (['name', 'waits', 'timeMs'] as const).forEach((key) => {
      labels[key] = waitLabel(key, row);
    });
    return {
      key: row.id,
      labels,
      values: {
        waits: row.waits ?? null,
        timeMs: row.timeMs ?? null
      },
      series: {}
    };
  })
);

const matchesQuery = (value: string, query: string) => (
  !query || value.toLowerCase().includes(query)
);

type DashText = Parameters<typeof mysqlCategoryText>[0];

const statementTableColumns = (
  t: DashText,
  source: readonly MysqlStatementRow[],
  defaultTimeShare: boolean
): LayeredColumn[] => statementColumns(source).map((key) => ({
  key,
  title: mysqlCategoryText(t, STATEMENT_TITLE_KEYS[key]),
  align: key === 'sql' ? 'left' as const : 'right' as const,
  ellipsis: key !== 'sql',
  defaultSortOrder: defaultTimeShare && key === 'timeShare' ? 'descend' as const : undefined,
  sorter: key === 'sql'
    ? (left, right) => (left.labels.sql || '').localeCompare(right.labels.sql || '')
    : (left, right) => compareNumber(left.values[key], right.values[key]),
  render: (entity: EntityTableRow) => (
    key === 'sql'
      ? <span className={pro.sqlCell}>{entity.labels.sql || '--'}</span>
      : (entity.labels[key] || '--')
  ),
  csvValue: (entity: EntityTableRow) => entity.labels[key] || '--'
}));

const waitTableColumnsOf = (
  t: DashText,
  source: readonly MysqlWaitEventRow[]
): LayeredColumn[] => waitColumns(source).map((key) => ({
  key,
  title: mysqlCategoryText(t, WAIT_TITLE_KEYS[key]),
  align: key === 'name' ? 'left' as const : 'right' as const,
  ellipsis: key !== 'name',
  defaultSortOrder: key === 'timeMs' ? 'descend' as const : undefined,
  sorter: key === 'name'
    ? (left, right) => (left.labels.name || '').localeCompare(right.labels.name || '')
    : (left, right) => (left.values[key] || 0) - (right.values[key] || 0),
  render: (entity: EntityTableRow) => entity.labels[key] || '--',
  csvValue: (entity: EntityTableRow) => entity.labels[key] || '--'
}));

function TableSearch({
  value,
  onChange,
  placeholder
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}) {
  return (
    <Input
      allowClear
      size="small"
      value={value}
      placeholder={placeholder}
      aria-label={placeholder}
      onChange={(event) => onChange(event.target.value)}
      className="w-52"
    />
  );
}

const csvHost = (instanceName: string) => instanceName.trim() || 'mysql';

function TabFill({
  loading,
  title,
  hint,
  actionLabel,
  onAction
}: {
  loading: boolean;
  title: string;
  hint?: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  if (loading) {
    return (
      <div className={`${host.kpiCard} ${host.kpiCardLoading}`} data-digest-state="loading">
        <ProDashLoading />
      </div>
    );
  }
  return (
    <GrayTabEmptyState
      title={title}
      hint={hint}
      actionLabel={actionLabel}
      onAction={onAction}
    />
  );
}

/** 主机磁盘挂载点短图：绘图区 160px，通栏，不另做第三套图壳。 */
function MountTrend({
  title,
  unit,
  points,
  legendLabel,
  color,
  loading,
  emptyText
}: {
  title: string;
  unit: 'ms' | 'counts';
  points?: Array<{ time: number; value: number }>;
  legendLabel: string;
  color: string;
  loading?: boolean;
  emptyText: string;
}) {
  return (
    <div className={host.diskMountChart}>
      <ThinTimeSeries
        title={title}
        unit={unit}
        loading={loading}
        data={trendData(points, legendLabel)}
        legends={[{ label: legendLabel, color }]}
        emptyText={emptyText}
      />
    </div>
  );
}

interface StatementPaneProps {
  rows: readonly MysqlStatementRow[];
  waits?: readonly MysqlWaitEventRow[];
  selectedId: string;
  onSelect: (id: string) => void;
  loading?: boolean;
  queryFailed?: boolean;
  instanceName: string;
  onOpenCollection?: () => void;
}

export function StatementPane({
  rows,
  waits = [],
  selectedId,
  onSelect,
  loading = false,
  queryFailed = false,
  instanceName,
  onOpenCollection
}: StatementPaneProps) {
  const { t } = useDashboardText();
  const [sqlQuery, setSqlQuery] = useState('');
  const query = sqlQuery.trim().toLowerCase();
  const visibleRows = rows.filter((row) => matchesQuery(row.sql || '', query));
  const selected = rows.find((row) => row.id === selectedId) || rows[0];
  const entities = statementEntities(visibleRows);
  const columns = statementTableColumns(t, rows, true);
  const primaryWait = selected ? primaryWaitForStatement(selected.id, waits) : null;
  const hasRows = rows.length > 0;
  if (!hasRows) {
    return (
      <TabFill
        loading={loading}
        title={mysqlCategoryText(t, queryFailed ? 'digestQueryFailedTitle' : 'emptyStatementsTitle')}
        hint={mysqlCategoryText(t, queryFailed ? 'digestQueryFailedHint' : 'emptyStatementsHint')}
        actionLabel={queryFailed || !onOpenCollection
          ? undefined
          : mysqlCategoryText(t, 'enableStatementCollection')}
        onAction={queryFailed ? undefined : onOpenCollection}
      />
    );
  }
  const trendEmpty = selected?.trend?.length
    ? mysqlCategoryText(t, 'statementNoTrend')
    : mysqlCategoryText(t, 'insufficientData');
  return (
    <div className={pro.chartStack}>
      <ProSectionTitle>{mysqlCategoryText(t, 'trend')}</ProSectionTitle>
      <MountTrend
        title={selected?.sql || mysqlCategoryText(t, 'statementTrend')}
        unit={rows.some((row) => row.totalTimeMs != null) ? 'ms' : 'counts'}
        points={selected?.trend}
        legendLabel={mysqlCategoryText(t, 'selectedStatement')}
        color={HOST_SERIES_COLOR.memUsed}
        loading={loading && !hasRows}
        emptyText={trendEmpty}
      />
      {primaryWait ? (
        <div className={host.shortcutSub}>
          {mysqlCategoryText(t, 'primaryWait', { name: primaryWait })}
        </div>
      ) : null}
      <ProSectionTitle>{mysqlCategoryText(t, 'statementList')}</ProSectionTitle>
      <LayeredEntityTable
        rows={entities}
        columns={columns}
        loading={loading}
        scrollY={false}
        selectedKey={selected?.id || ''}
        onSelect={onSelect}
        emptyText={emptyCopy({ title: mysqlCategoryText(t, 'noMatch') })}
        toolbar={(
          <div className="flex items-center gap-2">
            <TableSearch
              value={sqlQuery}
              onChange={setSqlQuery}
              placeholder={mysqlCategoryText(t, 'searchSql')}
            />
            <TableCsvExportButton
              host={csvHost(instanceName)}
              slug="statements"
              columns={columns}
              rows={entities}
            />
          </div>
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
  queryFailed?: boolean;
  instanceName: string;
  statementsCollected: boolean;
  onOpenCollection?: () => void;
}

export function WaitPane({
  rows,
  statements,
  selectedId,
  onSelect,
  loading = false,
  queryFailed = false,
  instanceName,
  statementsCollected,
  onOpenCollection
}: WaitPaneProps) {
  const { t } = useDashboardText();
  const [eventQuery, setEventQuery] = useState('');
  const query = eventQuery.trim().toLowerCase();
  const visibleRows = rows.filter((row) => matchesQuery(row.name || '', query));
  // 有列表就选中一行。当前 id 还在就保留，否则用排序后的第一行（常见是 idle）。
  const selected = rows.find((row) => row.id === selectedId) || rows[0] || null;
  const related = relatedStatementRows(selected, statements);
  const relatedRows = related ?? [];
  const waitTableRows = waitEntities(visibleRows);
  const waitTableColumns = waitTableColumnsOf(t, rows);
  const relatedTableRows = statementEntities(relatedRows);
  const relatedTableColumns = statementTableColumns(t, relatedRows, true);
  const exportHost = csvHost(instanceName);
  const hasRows = rows.length > 0;
  if (!hasRows) {
    return (
      <TabFill
        loading={loading}
        title={mysqlCategoryText(t, queryFailed ? 'digestQueryFailedTitle' : 'emptyWaitsTitle')}
        hint={mysqlCategoryText(t, queryFailed ? 'digestQueryFailedHint' : 'emptyWaitsHint')}
        actionLabel={queryFailed || !onOpenCollection
          ? undefined
          : mysqlCategoryText(t, 'enableWaitCollection')}
        onAction={queryFailed ? undefined : onOpenCollection}
      />
    );
  }
  const relatedEmpty = selected
    ? emptyCopy({
      title: mysqlCategoryText(t, 'noRelatedStatements'),
      hint: statementsCollected ? undefined : mysqlCategoryText(t, 'needStatementCollection'),
      actionLabel: statementsCollected || !onOpenCollection
        ? undefined
        : mysqlCategoryText(t, 'enableStatementCollection'),
      onAction: onOpenCollection
    })
    : emptyCopy({
      title: mysqlCategoryText(t, 'emptyStatementsTitle'),
      hint: mysqlCategoryText(t, 'emptyStatementsHint')
    });
  const waitTrendEmpty = selected
    ? (selected.trend?.length ? mysqlCategoryText(t, 'waitNoTrend') : mysqlCategoryText(t, 'insufficientData'))
    : mysqlCategoryText(t, 'selectToFollow');
  return (
    <div className={pro.chartStack}>
      <ProSectionTitle>{mysqlCategoryText(t, 'trend')}</ProSectionTitle>
      <MountTrend
        title={selected?.name || ''}
        unit="ms"
        points={selected?.trend}
        legendLabel={mysqlCategoryText(t, 'wait')}
        color={HOST_SERIES_COLOR.load1}
        loading={loading && !hasRows}
        emptyText={waitTrendEmpty}
      />
      <ProSectionTitle>{mysqlCategoryText(t, 'waitList')}</ProSectionTitle>
      <LayeredEntityTable
        rows={waitTableRows}
        columns={waitTableColumns}
        loading={loading}
        scrollY={false}
        selectedKey={selected?.id || ''}
        onSelect={(key) => {
          if (key) onSelect(key);
        }}
        emptyText={emptyCopy({ title: mysqlCategoryText(t, 'noMatch') })}
        toolbar={(
          <div className="flex items-center gap-2">
            <TableSearch
              value={eventQuery}
              onChange={setEventQuery}
              placeholder={mysqlCategoryText(t, 'searchWait')}
            />
            <TableCsvExportButton
              host={exportHost}
              slug="waits"
              columns={waitTableColumns}
              rows={waitTableRows}
            />
          </div>
        )}
      />
      <ProSectionTitle>{mysqlCategoryText(t, 'relatedStatements')}</ProSectionTitle>
      <LayeredEntityTable
        rows={relatedTableRows}
        columns={relatedTableColumns}
        loading={loading && statements.length === 0 && rows.length === 0}
        scrollY={false}
        selectedKey=""
        onSelect={() => undefined}
        emptyText={relatedEmpty}
        toolbar={(
          <TableCsvExportButton
            host={exportHost}
            slug="wait_statements"
            columns={relatedTableColumns}
            rows={relatedTableRows}
          />
        )}
      />
    </div>
  );
}

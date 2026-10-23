'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Input } from 'antd';
import { mergeChartSeries } from '../../../shared/utils/chart-data';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import type { EntityTableRow } from '../../host/entity-series';
import LayeredEntityTable, { type LayeredColumn } from '../../host/layered/entity-table';
import TableCsvExportButton from '../../host/layered/table-csv-export';
import { GrayTabEmptyState, ProDashLoading, ProSection, ThinTimeSeries, proChromeClass } from '../../host/layered/pro-chrome';
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
type ColumnSort = { key: string; order: 'ascend' | 'descend' } | null;

/** 缺数沉底：与主机表一样把 null 当作最小，降序时落在最后。相等时保持 ia 的次级顺序。 */
export const sortDigestRows = <T,>(
  rows: readonly T[],
  sort: ColumnSort,
  read: (row: T, key: string) => number | string | null | undefined
): T[] => {
  if (!sort) return [...rows];
  const factor = sort.order === 'ascend' ? 1 : -1;
  return [...rows].sort((left, right) => {
    const a = read(left, sort.key);
    const b = read(right, sort.key);
    if (typeof a === 'string' || typeof b === 'string') {
      return factor * String(a ?? '').localeCompare(String(b ?? ''));
    }
    return factor * compareNumber(typeof a === 'number' ? a : null, typeof b === 'number' ? b : null);
  });
};

const statementSortValue = (row: MysqlStatementRow, key: string) => (
  key === 'sql' ? row.sql || '' : row[key as StatementColumn]
);

const waitSortValue = (row: MysqlWaitEventRow, key: string) => (
  key === 'name' ? row.name || '' : row[key as WaitColumn]
);

const columnSortOrder = (key: string, sort: ColumnSort) => (
  sort?.key === key ? sort.order : null
);

const sameSort = (current: ColumnSort, next: ColumnSort): ColumnSort => (
  current?.key === next?.key && current?.order === next?.order ? current : next
);

const readColumnSort = (
  sorter: { columnKey?: React.Key; order?: 'ascend' | 'descend' | null }
    | readonly { columnKey?: React.Key; order?: 'ascend' | 'descend' | null }[]
): ColumnSort => {
  const current = Array.isArray(sorter) ? sorter[0] : sorter;
  if (!current?.order || current.columnKey == null) return null;
  return { key: String(current.columnKey), order: current.order };
};

const statementTableColumns = (
  t: DashText,
  source: readonly MysqlStatementRow[],
  sort: ColumnSort
): LayeredColumn[] => statementColumns(source).map((key) => ({
  key,
  title: mysqlCategoryText(t, STATEMENT_TITLE_KEYS[key]),
  align: key === 'sql' ? 'left' as const : 'right' as const,
  ellipsis: key !== 'sql',
  sortOrder: columnSortOrder(key, sort),
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
  source: readonly MysqlWaitEventRow[],
  sort: ColumnSort
): LayeredColumn[] => waitColumns(source).map((key) => ({
  key,
  title: mysqlCategoryText(t, WAIT_TITLE_KEYS[key]),
  align: key === 'name' ? 'left' as const : 'right' as const,
  ellipsis: key !== 'name',
  sortOrder: columnSortOrder(key, sort),
  sorter: key === 'name'
    ? (left, right) => (left.labels.name || '').localeCompare(right.labels.name || '')
    : (left, right) => compareNumber(left.values[key], right.values[key]),
  render: (entity: EntityTableRow) => entity.labels[key] || '--',
  csvValue: (entity: EntityTableRow) => entity.labels[key] || '--'
}));

const { Search } = Input;

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
    <Search
      allowClear
      size="small"
      enterButton
      value={value}
      placeholder={placeholder}
      aria-label={placeholder}
      onChange={(event) => onChange(event.target.value)}
      onSearch={onChange}
      className="w-60 max-w-full"
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
      <div className={`${proChromeClass.kpiCard} ${proChromeClass.kpiCardLoading}`} data-digest-state="loading">
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
  const [statementSort, setStatementSort] = useState<ColumnSort>({ key: 'timeShare', order: 'descend' });
  const query = sqlQuery.trim().toLowerCase();
  const ordered = useMemo(
    () => sortDigestRows(
      rows.filter((row) => matchesQuery(row.sql || '', query)),
      statementSort,
      statementSortValue
    ),
    [rows, query, statementSort]
  );
  const selected = ordered.find((row) => row.id === selectedId)
    || ordered[0]
    || rows.find((row) => row.id === selectedId)
    || rows[0];
  useEffect(() => {
    if (!ordered.length) return;
    if (selectedId && ordered.some((row) => row.id === selectedId)) return;
    onSelect(ordered[0].id);
  }, [ordered, selectedId, onSelect]);
  const entities = statementEntities(ordered);
  const columns = statementTableColumns(t, rows, statementSort);
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
      <ProSection title={mysqlCategoryText(t, 'trend')}>
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
        <div className={proChromeClass.shortcutSub}>
          {mysqlCategoryText(t, 'primaryWait', { name: primaryWait })}
        </div>
      ) : null}
      </ProSection>
      <ProSection title={mysqlCategoryText(t, 'statementList')}>
      <LayeredEntityTable
        rows={entities}
        columns={columns}
        loading={loading}
        scrollY={false}
        selectedKey={ordered.some((row) => row.id === selected?.id) ? selected?.id || '' : ''}
        onSelect={onSelect}
        onChange={(_pagination, _filters, sorter) => {
          setStatementSort((current) => sameSort(current, readColumnSort(sorter)));
        }}
        emptyText={emptyCopy({ title: mysqlCategoryText(t, 'noMatch') })}
        toolbar={(
          <div className="flex w-full min-w-0 flex-wrap items-center gap-2">
            <TableSearch
              value={sqlQuery}
              onChange={setSqlQuery}
              placeholder={mysqlCategoryText(t, 'searchSql')}
            />
            <div className="ml-auto">
              <TableCsvExportButton
                host={csvHost(instanceName)}
                slug="statements"
                columns={columns}
                rows={entities}
              />
            </div>
          </div>
        )}
      />
      </ProSection>
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
  const [waitSort, setWaitSort] = useState<ColumnSort>({ key: 'timeMs', order: 'descend' });
  const [relatedSort, setRelatedSort] = useState<ColumnSort>({ key: 'timeShare', order: 'descend' });
  const query = eventQuery.trim().toLowerCase();
  const ordered = useMemo(
    () => sortDigestRows(
      rows.filter((row) => matchesQuery(row.name || '', query)),
      waitSort,
      waitSortValue
    ),
    [rows, query, waitSort]
  );
  // 原选中还在过滤结果里就保持，否则用当前排序后的第一行。
  const selected = ordered.find((row) => row.id === selectedId)
    || ordered[0]
    || rows.find((row) => row.id === selectedId)
    || rows[0]
    || null;
  useEffect(() => {
    if (!ordered.length) return;
    if (selectedId && ordered.some((row) => row.id === selectedId)) return;
    onSelect(ordered[0].id);
  }, [ordered, selectedId, onSelect]);
  const related = relatedStatementRows(selected, statements);
  const relatedRows = related ?? [];
  const relatedOrdered = useMemo(
    () => sortDigestRows(relatedRows, relatedSort, statementSortValue),
    [relatedRows, relatedSort]
  );
  const waitTableRows = waitEntities(ordered);
  const waitTableColumns = waitTableColumnsOf(t, rows, waitSort);
  const relatedTableRows = statementEntities(relatedOrdered);
  const relatedTableColumns = statementTableColumns(t, relatedRows, relatedSort);
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
      <ProSection title={mysqlCategoryText(t, 'trend')}>
      <MountTrend
        title={selected?.name || ''}
        unit="ms"
        points={selected?.trend}
        legendLabel={mysqlCategoryText(t, 'wait')}
        color={HOST_SERIES_COLOR.load1}
        loading={loading && !hasRows}
        emptyText={waitTrendEmpty}
      />
      </ProSection>
      <ProSection title={mysqlCategoryText(t, 'waitList')}>
      <LayeredEntityTable
        rows={waitTableRows}
        columns={waitTableColumns}
        loading={loading}
        scrollY={false}
        selectedKey={ordered.some((row) => row.id === selected?.id) ? selected?.id || '' : ''}
        onSelect={(key) => {
          if (key) onSelect(key);
        }}
        onChange={(_pagination, _filters, sorter) => {
          setWaitSort((current) => sameSort(current, readColumnSort(sorter)));
        }}
        emptyText={emptyCopy({ title: mysqlCategoryText(t, 'noMatch') })}
        toolbar={(
          <div className="flex w-full min-w-0 flex-wrap items-center gap-2">
            <TableSearch
              value={eventQuery}
              onChange={setEventQuery}
              placeholder={mysqlCategoryText(t, 'searchWait')}
            />
            <div className="ml-auto">
              <TableCsvExportButton
                host={exportHost}
                slug="waits"
                columns={waitTableColumns}
                rows={waitTableRows}
              />
            </div>
          </div>
        )}
      />
      </ProSection>
      <ProSection title={mysqlCategoryText(t, 'relatedStatements')}>
      <LayeredEntityTable
        rows={relatedTableRows}
        columns={relatedTableColumns}
        loading={loading && statements.length === 0 && rows.length === 0}
        scrollY={false}
        selectedKey=""
        onSelect={() => undefined}
        onChange={(_pagination, _filters, sorter) => {
          setRelatedSort((current) => sameSort(current, readColumnSort(sorter)));
        }}
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
      </ProSection>
    </div>
  );
}

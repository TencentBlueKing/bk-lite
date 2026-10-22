'use client';

import React from 'react';
import { mergeChartSeries } from '../../../shared/utils/chart-data';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import type { EntityTableRow } from '../../host/entity-series';
import LayeredEntityTable from '../../host/layered/entity-table';
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

const statementEntities = (rows: readonly MysqlStatementRow[]): EntityTableRow[] => (
  rows.map((row) => {
    const labels: Record<string, string> = {};
    statementColumns(rows).forEach((key) => {
      labels[key] = statementLabel(key, row);
    });
    return { key: row.id, labels, values: {}, series: {} };
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
    waitColumns(rows).forEach((key) => {
      labels[key] = waitLabel(key, row);
    });
    return { key: row.id, labels, values: {}, series: {} };
  })
);

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
  const selected = rows.find((row) => row.id === selectedId) || rows[0];
  const entities = statementEntities(rows);
  const columns = statementColumns(rows).map((key) => ({
    key,
    title: mysqlCategoryText(t, STATEMENT_TITLE_KEYS[key]),
    align: key === 'sql' ? 'left' as const : 'right' as const,
    ellipsis: key !== 'sql',
    render: (entity: EntityTableRow) => (
      key === 'sql'
        ? <span className={pro.sqlCell}>{entity.labels.sql || '--'}</span>
        : (entity.labels[key] || '--')
    ),
    csvValue: (entity: EntityTableRow) => entity.labels[key] || '--'
  }));
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
        emptyText={emptyCopy({
          title: mysqlCategoryText(t, 'emptyStatementsTitle'),
          hint: mysqlCategoryText(t, 'emptyStatementsHint')
        })}
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
  // 有列表就选中一行。当前 id 还在就保留，否则用排序后的第一行（常见是 idle）。
  const selected = rows.find((row) => row.id === selectedId) || rows[0] || null;
  const related = relatedStatementRows(selected, statements);
  const relatedRows = related ?? [];
  const waitTableRows = waitEntities(rows);
  const waitTableColumns = waitColumns(rows).map((key) => ({
    key,
    title: mysqlCategoryText(t, WAIT_TITLE_KEYS[key]),
    align: key === 'name' ? 'left' as const : 'right' as const,
    ellipsis: key !== 'name',
    render: (entity: EntityTableRow) => entity.labels[key] || '--',
    csvValue: (entity: EntityTableRow) => entity.labels[key] || '--'
  }));
  const relatedTableRows = statementEntities(relatedRows);
  const relatedTableColumns = statementColumns(relatedRows).map((key) => ({
    key,
    title: mysqlCategoryText(t, STATEMENT_TITLE_KEYS[key]),
    align: key === 'sql' ? 'left' as const : 'right' as const,
    ellipsis: key !== 'sql',
    render: (entity: EntityTableRow) => (
      key === 'sql'
        ? <span className={pro.sqlCell}>{entity.labels.sql || '--'}</span>
        : (entity.labels[key] || '--')
    ),
    csvValue: (entity: EntityTableRow) => entity.labels[key] || '--'
  }));
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
        emptyText={emptyCopy({
          title: mysqlCategoryText(t, 'emptyWaitsTitle'),
          hint: mysqlCategoryText(t, 'emptyWaitsHint')
        })}
        toolbar={(
          <TableCsvExportButton
            host={exportHost}
            slug="waits"
            columns={waitTableColumns}
            rows={waitTableRows}
          />
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

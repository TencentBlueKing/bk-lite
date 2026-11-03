'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Input } from 'antd';
import { mergeChartSeries } from '../../../shared/utils/chart-data';
import type { EntityTableRow } from '../../host/entity-series';
import LayeredEntityTable, { type LayeredColumn } from '../../host/layered/entity-table';
import TableCsvExportButton from '../../host/layered/table-csv-export';
import { GrayTabEmptyState, ProDashLoading, ProSection, ThinTimeSeries, proChromeClass } from '../../host/layered/pro-chrome';
import host from '../../host/layered/layered.module.scss';
import { HOST_SERIES_COLOR } from '../../host/config';
import {
  formatAverageLatency,
  formatCount,
  formatTimeShare,
  statementDatabaseFilters,
  statementMatchesDatabases,
  type PostgresStatementRow,
  type PostgresWaitRow
} from './digest';

const trendData = (points: Array<{ time: number; value: number }> | undefined, label: string) => (
  mergeChartSeries([{
    key: 'value',
    label,
    data: (points || [])
      .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.value))
      .map((point) => ({ time: point.time, value1: point.value }))
  }])
);

const compareNumber = (left: number | null | undefined, right: number | null | undefined) => {
  const a = left == null || !Number.isFinite(left) ? Number.NEGATIVE_INFINITY : left;
  const b = right == null || !Number.isFinite(right) ? Number.NEGATIVE_INFINITY : right;
  return a - b;
};

type ColumnSort = { key: string; order: 'ascend' | 'descend' } | null;

const sortRows = <T,>(
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

const readSort = (
  sorter: { columnKey?: React.Key; order?: 'ascend' | 'descend' | null }
    | readonly { columnKey?: React.Key; order?: 'ascend' | 'descend' | null }[]
): ColumnSort => {
  const current = Array.isArray(sorter) ? sorter[0] : sorter;
  if (!current?.order || current.columnKey == null) return null;
  return { key: String(current.columnKey), order: current.order };
};

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
      <div className={`${proChromeClass.kpiCard} ${proChromeClass.kpiCardLoading}`} data-postgres-digest="loading">
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

function Trend({
  title,
  unit,
  points,
  legendLabel,
  color,
  emptyText
}: {
  title: string;
  unit: 'ms' | 'counts';
  points?: Array<{ time: number; value: number }>;
  legendLabel: string;
  color: string;
  emptyText: string;
}) {
  return (
    <div className={host.diskMountChart}>
      <ThinTimeSeries
        title={title}
        unit={unit}
        data={trendData(points, legendLabel)}
        legends={[{ label: legendLabel, color }]}
        emptyText={emptyText}
      />
    </div>
  );
}

const { Search } = Input;

const statementValue = (row: PostgresStatementRow, key: string) => {
  if (key === 'sql') return row.sql;
  if (key === 'datname') return row.datname;
  if (key === 'timeShare') return row.timeShare;
  if (key === 'calls') return row.calls;
  if (key === 'avgSeconds') return row.avgSeconds;
  return row.rowsReturned;
};

export function StatementPane({
  rows,
  selectedId,
  onSelect,
  loading = false,
  queryFailed = false,
  instanceName,
  onOpenCollection
}: {
  rows: readonly PostgresStatementRow[];
  selectedId: string;
  onSelect: (id: string) => void;
  loading?: boolean;
  queryFailed?: boolean;
  instanceName: string;
  onOpenCollection?: () => void;
}) {
  const [queryText, setQueryText] = useState('');
  const [databases, setDatabases] = useState<string[]>([]);
  const [sort, setSort] = useState<ColumnSort>({ key: 'timeShare', order: 'descend' });
  const query = queryText.trim().toLowerCase();
  const databaseFilters = useMemo(() => statementDatabaseFilters(rows), [rows]);
  const ordered = useMemo(
    () => sortRows(
      rows.filter((row) => (
        statementMatchesDatabases(row.datname, databases)
        && (!query || `${row.sql} ${row.datname}`.toLowerCase().includes(query))
      )),
      sort,
      statementValue
    ),
    [databases, query, rows, sort]
  );
  const selected = ordered.find((row) => row.id === selectedId) || ordered[0];
  useEffect(() => {
    if (!ordered.length) return;
    if (selectedId && ordered.some((row) => row.id === selectedId)) return;
    onSelect(ordered[0].id);
  }, [onSelect, ordered, selectedId]);
  useEffect(() => {
    setDatabases((current) => {
      if (!current.length) return current;
      const allowed = new Set(databaseFilters.map((item) => item.value));
      const next = current.filter((name) => allowed.has(name));
      return next.length === current.length ? current : next;
    });
  }, [databaseFilters]);
  if (!rows.length) {
    return (
      <TabFill
        loading={loading}
        title={queryFailed ? '暂时无法显示' : '暂无 Top SQL 数据'}
        hint={queryFailed
          ? '当前窗口没有返回可用结果。请稍后重试，无需为此重新开启采集。'
          : '请在采集配置中开启「Top SQL 采集」，并确认目标库已安装 pg_stat_statements，监控账号可以读取它。若已开启，保存配置后请稍候，下一次采集完成即可显示。'}
        actionLabel={queryFailed || !onOpenCollection ? undefined : '去开启 Top SQL 采集'}
        onAction={queryFailed ? undefined : onOpenCollection}
      />
    );
  }
  const columns: LayeredColumn[] = [
    {
      key: 'sql',
      title: '语句',
      render: (entity) => <span className="break-words font-mono text-[12px] whitespace-normal">{entity.labels.sql || '--'}</span>,
      csvValue: (entity) => entity.labels.sql || '--',
      sorter: (left, right) => (left.labels.sql || '').localeCompare(right.labels.sql || ''),
      sortOrder: sort?.key === 'sql' ? sort.order : null
    },
    {
      key: 'datname',
      title: '数据库',
      render: (entity) => entity.labels.datname || '--',
      csvValue: (entity) => entity.labels.datname || '--',
      sorter: (left, right) => (left.labels.datname || '').localeCompare(right.labels.datname || ''),
      sortOrder: sort?.key === 'datname' ? sort.order : null,
      filters: databaseFilters,
      filterMultiple: true,
      filteredValue: databases.length ? databases : null
    },
    {
      key: 'timeShare',
      title: '耗时占比',
      align: 'right',
      render: (entity) => entity.labels.timeShare || '--',
      csvValue: (entity) => entity.labels.timeShare || '--',
      sorter: (left, right) => compareNumber(left.values.timeShare, right.values.timeShare),
      sortOrder: sort?.key === 'timeShare' ? sort.order : null
    },
    {
      key: 'calls',
      title: '执行次数',
      align: 'right',
      width: 132,
      minWidth: 132,
      ellipsis: false,
      render: (entity) => <span className="whitespace-nowrap tabular-nums">{entity.labels.calls || '--'}</span>,
      csvValue: (entity) => entity.labels.calls || '--',
      sorter: (left, right) => compareNumber(left.values.calls, right.values.calls),
      sortOrder: sort?.key === 'calls' ? sort.order : null
    },
    {
      key: 'avgSeconds',
      title: '平均耗时',
      align: 'right',
      render: (entity) => entity.labels.avgSeconds || '--',
      csvValue: (entity) => entity.labels.avgSeconds || '--',
      sorter: (left, right) => compareNumber(left.values.avgSeconds, right.values.avgSeconds),
      sortOrder: sort?.key === 'avgSeconds' ? sort.order : null
    },
    {
      key: 'rowsReturned',
      title: '返回行',
      align: 'right',
      render: (entity) => entity.labels.rowsReturned || '--',
      csvValue: (entity) => entity.labels.rowsReturned || '--',
      sorter: (left, right) => compareNumber(left.values.rowsReturned, right.values.rowsReturned),
      sortOrder: sort?.key === 'rowsReturned' ? sort.order : null
    }
  ];
  const entities: EntityTableRow[] = ordered.map((row) => ({
    key: row.id,
    labels: {
      sql: row.sql || '--',
      datname: row.datname || '--',
      timeShare: formatTimeShare(row.timeShare),
      calls: formatCount(row.calls),
      avgSeconds: formatAverageLatency(row.avgSeconds),
      rowsReturned: formatCount(row.rowsReturned)
    },
    values: {
      timeShare: row.timeShare ?? null,
      calls: row.calls ?? null,
      avgSeconds: row.avgSeconds ?? null,
      rowsReturned: row.rowsReturned ?? null
    },
    series: {}
  }));
  return (
    <div className="flex flex-col gap-3">
      <ProSection title="趋势">
        <Trend
          title={selected?.sql || '语句趋势'}
          unit="ms"
          points={selected?.trend}
          legendLabel="选中语句"
          color={HOST_SERIES_COLOR.memUsed}
          emptyText={ordered.length ? '数据不足' : '无匹配项'}
        />
      </ProSection>
      <ProSection title="Top SQL 列表">
        <LayeredEntityTable
          rows={entities}
          columns={columns}
          loading={loading}
          scrollY={false}
          selectedKey={selected?.id || ''}
          onSelect={onSelect}
          onChange={(_pagination, filters, sorter) => {
            setSort(readSort(sorter));
            const picked = filters?.datname;
            setDatabases(Array.isArray(picked) ? picked.map(String) : []);
          }}
          emptyText="无匹配项"
          toolbar={(
            <div className="flex w-full min-w-0 flex-wrap items-center gap-2">
              <Search
                allowClear
                size="small"
                enterButton
                value={queryText}
                placeholder="搜索语句"
                aria-label="搜索语句"
                onChange={(event) => setQueryText(event.target.value)}
                onSearch={setQueryText}
                className="w-60 max-w-full"
              />
              <div className="ml-auto">
                <TableCsvExportButton
                  host={instanceName.trim() || 'postgres'}
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

export function WaitPane({
  rows,
  selectedId,
  onSelect,
  loading = false,
  queryFailed = false,
  instanceName,
  onOpenCollection
}: {
  rows: readonly PostgresWaitRow[];
  selectedId: string;
  onSelect: (id: string) => void;
  loading?: boolean;
  queryFailed?: boolean;
  instanceName: string;
  onOpenCollection?: () => void;
}) {
  const [queryText, setQueryText] = useState('');
  const [sort, setSort] = useState<ColumnSort>({ key: 'sessions', order: 'descend' });
  const query = queryText.trim().toLowerCase();
  const ordered = useMemo(
    () => sortRows(
      rows.filter((row) => !query || row.name.toLowerCase().includes(query)),
      sort,
      (row, key) => (key === 'name' ? row.name : row.sessions)
    ),
    [query, rows, sort]
  );
  const selected = ordered.find((row) => row.id === selectedId) || ordered[0] || rows[0];
  useEffect(() => {
    if (!ordered.length) return;
    if (selectedId && ordered.some((row) => row.id === selectedId)) return;
    onSelect(ordered[0].id);
  }, [onSelect, ordered, selectedId]);
  if (!rows.length) {
    return (
      <TabFill
        loading={loading}
        title={queryFailed ? '暂时无法显示' : '暂无等待数据'}
        hint={queryFailed
          ? '当前窗口没有返回可用结果。请稍后重试，无需为此重新开启采集。'
          : '请在采集配置中开启「等待事件采集」。开启后这里显示当前正在等待的会话；当时没有会话处于等待时，这里也会是空的。若已开启，保存配置后请稍候，下一次采集完成即可显示。'}
        actionLabel={queryFailed || !onOpenCollection ? undefined : '去开启等待事件采集'}
        onAction={queryFailed ? undefined : onOpenCollection}
      />
    );
  }
  const columns: LayeredColumn[] = [
    {
      key: 'name',
      title: '等待事件',
      render: (entity) => entity.labels.name || '--',
      csvValue: (entity) => entity.labels.name || '--',
      sorter: (left, right) => (left.labels.name || '').localeCompare(right.labels.name || ''),
      sortOrder: sort?.key === 'name' ? sort.order : null
    },
    {
      key: 'sessions',
      title: '当前会话',
      align: 'right',
      render: (entity) => entity.labels.sessions || '--',
      csvValue: (entity) => entity.labels.sessions || '--',
      sorter: (left, right) => compareNumber(left.values.sessions, right.values.sessions),
      sortOrder: sort?.key === 'sessions' ? sort.order : null
    }
  ];
  const entities: EntityTableRow[] = ordered.map((row) => ({
    key: row.id,
    labels: {
      name: row.name || '--',
      sessions: formatCount(row.sessions)
    },
    values: { sessions: row.sessions ?? null },
    series: {}
  }));
  return (
    <div className="flex flex-col gap-3">
      <ProSection title="趋势">
        <Trend
          title={selected?.name || '等待会话'}
          unit="counts"
          points={selected?.trend}
          legendLabel="当前会话"
          color={HOST_SERIES_COLOR.load1}
          emptyText="数据不足"
        />
      </ProSection>
      <ProSection title="等待列表">
        <LayeredEntityTable
          rows={entities}
          columns={columns}
          loading={loading}
          scrollY={false}
          selectedKey={selected?.id || ''}
          onSelect={(key) => {
            if (key) onSelect(key);
          }}
          onChange={(_pagination, _filters, sorter) => setSort(readSort(sorter))}
          emptyText="无匹配项"
          toolbar={(
            <div className="flex w-full min-w-0 flex-wrap items-center gap-2">
              <Search
                allowClear
                size="small"
                enterButton
                value={queryText}
                placeholder="搜索等待事件"
                aria-label="搜索等待事件"
                onChange={(event) => setQueryText(event.target.value)}
                onSearch={setQueryText}
                className="w-60 max-w-full"
              />
              <div className="ml-auto">
                <TableCsvExportButton
                  host={instanceName.trim() || 'postgres'}
                  slug="waits"
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

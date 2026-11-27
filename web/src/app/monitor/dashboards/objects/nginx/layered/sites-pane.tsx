'use client';

import { useMemo, useState, type ReactNode } from 'react';
import { ProSection } from '../../host/layered/section-title';
import { byteScale, durationUnitLabel, formatBytes, formatBytesPerSecond, formatCount, formatDuration, formatPerSecond, pickDurationUnit } from './format';
import { NGINX_HINTS } from './hints';
import { NGINX_SPAN, NginxChartCard, NginxRankCard, NginxRetryBanner } from './nginx-card';
import { NginxCompositionCard } from './nginx-composition';
import { NginxHint } from './nginx-hint';
import { filterPlotted } from './selection';
import type { FilterTableRow, NginxDashboardModel, ZoneTableRow } from './model';
import { NGINX_CARD_QUERIES, phaseOf, type NginxQueryPhase } from './query-phase';
import { ProMetricTable, type ProMetricColumn, type ProMetricRow } from '../../../shared/widgets/pro-metric-table';

const STATUS_COLORS: Record<string, string> = {
  '1xx': '#8c8c8c',
  '2xx': '#27c274',
  '3xx': '#2f6bff',
  '4xx': '#ff8a1f',
  '5xx': '#ff4d4f'
};

const STATUS_ORDER = ['1xx', '2xx', '3xx', '4xx', '5xx'] as const;
const SITE_EMPTY_DETAIL = '窗口内没有请求';

type ZoneSortKey = 'zone' | 'rate' | 'window' | '1xx' | '2xx' | '3xx' | '4xx' | '5xx' | 'in' | 'out' | 'time';
type FilterSortKey = 'name' | 'key' | 'rate' | 'window' | '2xx' | '4xx' | '5xx' | 'in' | 'out' | 'time';

const textOf = (value: number | null | undefined, text: string) => (value == null ? '--' : text);

const zoneNumber = (row: ZoneTableRow, key: ZoneSortKey) => {
  if (key === 'rate') return row.requestRate;
  if (key === 'window') return row.windowRequests ?? null;
  if (key === 'in') return row.windowBytesIn ?? null;
  if (key === 'out') return row.windowBytesOut ?? null;
  if (key === 'time') return row.timeMs;
  if (key === 'zone') return null;
  return row.windowCodes?.[key] ?? null;
};

const filterNumber = (row: FilterTableRow, key: FilterSortKey) => {
  if (key === 'rate') return row.requestRate;
  if (key === 'window') return row.windowRequests ?? null;
  if (key === 'in') return row.windowBytesIn ?? null;
  if (key === 'out') return row.windowBytesOut ?? null;
  if (key === 'time') return row.timeMs;
  if (key === '2xx' || key === '4xx' || key === '5xx') return row.windowCodes?.[key] ?? null;
  return null;
};

const byNumber = (left: number | null, right: number | null, desc: boolean) => {
  const delta = (right ?? Number.NEGATIVE_INFINITY) - (left ?? Number.NEGATIVE_INFINITY);
  return desc ? delta : -delta;
};

export default function SitesPane({
  model,
  phases,
  emptyText,
  onRetry,
  onRetryFailed
}: {
  model: NginxDashboardModel;
  phases: Readonly<Record<string, NginxQueryPhase>>;
  emptyText: string;
  onRetry: (keys: readonly string[]) => void;
  onRetryFailed: () => void;
}) {
  const [sortKey, setSortKey] = useState<ZoneSortKey>('rate');
  const [sortDesc, setSortDesc] = useState(true);
  const [filterSort, setFilterSort] = useState<FilterSortKey>('rate');
  const [filterDesc, setFilterDesc] = useState(true);
  const [zone, setZone] = useState<string | null>(null);
  const board = model.board;
  const statusPhase = phaseOf(NGINX_CARD_QUERIES.sitesStatus, phases);
  const trafficPhase = phaseOf(NGINX_CARD_QUERIES.sitesTraffic, phases);
  const timePhase = phaseOf(NGINX_CARD_QUERIES.sitesTime, phases);
  const rankPhase = phaseOf(NGINX_CARD_QUERIES.sitesRank, phases);
  const tablePhase = phaseOf(NGINX_CARD_QUERIES.sitesTable, phases);
  const filterPhase = phaseOf(NGINX_CARD_QUERIES.filterTable, phases);
  const cardPhases = [statusPhase, statusPhase, trafficPhase, timePhase, rankPhase, rankPhase, tablePhase];
  if (model.showFilter) cardPhases.push(filterPhase);
  const failures = cardPhases.filter((item) => item === 'error').length;
  const rows = useMemo(() => [...model.zoneRows].sort((left, right) => {
    if (sortKey === 'zone') {
      const delta = left.zone.localeCompare(right.zone, 'zh');
      return sortDesc ? -delta : delta;
    }
    return byNumber(zoneNumber(left, sortKey), zoneNumber(right, sortKey), sortDesc);
  }), [model.zoneRows, sortDesc, sortKey]);
  const filterRows = useMemo(() => [...model.filterRows].sort((left, right) => {
    if (filterSort === 'name' || filterSort === 'key') {
      const delta = (filterSort === 'name' ? left.filterName : left.filterKey).localeCompare(
        filterSort === 'name' ? right.filterName : right.filterKey,
        'zh'
      );
      return filterDesc ? -delta : delta;
    }
    return byNumber(filterNumber(left, filterSort), filterNumber(right, filterSort), filterDesc);
  }), [filterDesc, filterSort, model.filterRows]);
  const show1xx = [...rows, model.zoneSummary].some((row) => (row?.windowCodes?.['1xx'] ?? 0) > 0);
  const trend = zone ? filterPlotted(model.zoneRequest, new Set([zone])) : board.siteTrend;
  const bytePeak = board.trafficSeries.reduce((peak, item) => Math.max(peak, ...item.points.map((point) => Math.abs(point.value))), 0);
  const scale = byteScale(bytePeak);
  const chooseSort = (key: string) => {
    const next = key as ZoneSortKey;
    if (sortKey === next) setSortDesc((value) => !value);
    else {
      setSortKey(next);
      setSortDesc(true);
    }
  };
  const chooseFilterSort = (key: string) => {
    const next = key as FilterSortKey;
    if (filterSort === next) setFilterDesc((value) => !value);
    else {
      setFilterSort(next);
      setFilterDesc(true);
    }
  };
  const tableTimeUnit = pickDurationUnit([
    ...model.zoneRows.map((row) => row.timeMs),
    model.zoneSummary?.timeMs
  ].reduce((peak, value) => (
    value != null && Number.isFinite(value) ? Math.max(peak, Math.abs(value)) : peak
  ), 0));
  const zoneColumns: ProMetricColumn[] = [
    { key: 'zone', label: '站点', align: 'left', minWidth: 160 },
    { key: 'rate', label: '请求速率', align: 'right' },
    { key: 'window', label: '窗口请求数', align: 'right' },
    ...(show1xx ? [{ key: '1xx', label: '1xx', align: 'right' as const }] : []),
    { key: '2xx', label: '2xx', align: 'right' },
    { key: '3xx', label: '3xx', align: 'right' },
    { key: '4xx', label: '4xx', align: 'right' },
    { key: '5xx', label: '5xx', align: 'right' },
    { key: 'in', label: '入站', align: 'right' },
    { key: 'out', label: '出站', align: 'right' },
    { key: 'time', label: '平均处理时间', align: 'right' }
  ];
  const zoneCsv = (row: ZoneTableRow, name: string) => zoneColumns.map((column) => {
    if (column.key === 'zone') return name;
    if (column.key === 'rate') return textOf(row.requestRate, formatPerSecond(row.requestRate ?? 0, '次'));
    if (column.key === 'window') return textOf(row.windowRequests ?? null, formatCount(row.windowRequests ?? 0, '次'));
    if (column.key === 'in') return textOf(row.windowBytesIn ?? null, formatBytes(row.windowBytesIn ?? 0));
    if (column.key === 'out') return textOf(row.windowBytesOut ?? null, formatBytes(row.windowBytesOut ?? 0));
    if (column.key === 'time') return textOf(row.timeMs, formatDuration(row.timeMs ?? 0, tableTimeUnit));
    const code = row.windowCodes?.[column.key] ?? null;
    return textOf(code, formatCount(code ?? 0, '次'));
  });
  const zoneCells = (row: ZoneTableRow, name: string): ReactNode[] => zoneCsv(row, name).map((value, index) => (
    index === 0
      ? <span key={name} className="block max-w-[240px] truncate" title={name}>{name}</span>
      : value
  ));
  const zoneTableRows: ProMetricRow[] = rows.map((row) => ({
    key: row.zone,
    cells: zoneCells(row, row.zone),
    csv: zoneCsv(row, row.zone)
  }));
  const zoneFooter: ProMetricRow | null = model.zoneSummary ? {
    key: 'total',
    cells: zoneCells(model.zoneSummary, '全部站点'),
    csv: zoneCsv(model.zoneSummary, '全部站点')
  } : null;
  const filterColumns: ProMetricColumn[] = [
    { key: 'name', label: '过滤器', align: 'left', minWidth: 160 },
    { key: 'key', label: '过滤键', align: 'left' },
    { key: 'rate', label: '请求速率', align: 'right' },
    { key: 'window', label: '窗口请求数', align: 'right' },
    { key: '2xx', label: '2xx', align: 'right' },
    { key: '4xx', label: '4xx', align: 'right' },
    { key: '5xx', label: '5xx', align: 'right' },
    { key: 'in', label: '入站', align: 'right' },
    { key: 'out', label: '出站', align: 'right' },
    { key: 'time', label: '平均处理时间', align: 'right' }
  ];
  const filterCsv = (row: FilterTableRow) => [
    row.filterName,
    row.filterKey || '--',
    textOf(row.requestRate, formatPerSecond(row.requestRate ?? 0, '次')),
    textOf(row.windowRequests ?? null, formatCount(row.windowRequests ?? 0, '次')),
    textOf(row.windowCodes?.['2xx'] ?? null, formatCount(row.windowCodes?.['2xx'] ?? 0, '次')),
    textOf(row.windowCodes?.['4xx'] ?? null, formatCount(row.windowCodes?.['4xx'] ?? 0, '次')),
    textOf(row.windowCodes?.['5xx'] ?? null, formatCount(row.windowCodes?.['5xx'] ?? 0, '次')),
    textOf(row.windowBytesIn ?? null, formatBytes(row.windowBytesIn ?? 0)),
    textOf(row.windowBytesOut ?? null, formatBytes(row.windowBytesOut ?? 0)),
    textOf(row.timeMs, formatDuration(row.timeMs ?? 0, model.zoneTimeUnit))
  ];
  const filterTableRows: ProMetricRow[] = filterRows.map((row) => {
    const csv = filterCsv(row);
    return {
      key: `${row.filterName}|${row.filterKey}`,
      csv,
      cells: csv.map((value, index) => (
        index === 0
          ? <span key={value} className="block max-w-[220px] truncate" title={row.filterName}>{row.filterName}</span>
          : value
      ))
    };
  });
  const statusBlocked = board.windowRequests === '暂无数据' || board.windowRequests === '0';
  const statusParts = STATUS_ORDER.map((code) => ({
    id: code,
    label: code,
    color: STATUS_COLORS[code],
    value: statusBlocked ? null : (board.statusParts.find((part) => part.code === code)?.count ?? 0)
  }));
  const tableEmpty = tablePhase !== 'ready' ? (
    <NginxChartCard title="" items={[]} floor={1} formatReading={() => ''} phase={tablePhase} emptyText={emptyText} onRetry={() => onRetry(NGINX_CARD_QUERIES.sitesTable)} height={300} />
  ) : !rows.length && !model.zoneSummary ? (
    <div className="flex flex-1 items-center justify-center text-[14px] text-[var(--color-text-3)]">{emptyText}</div>
  ) : undefined;

  return (
    <div className="flex flex-col gap-6" data-nginx-pane="sites">
      <NginxRetryBanner visible={failures >= 3} onRetry={onRetryFailed} />
      <ProSection id="nginx-status-section" title="状态码">
        <div className="grid grid-cols-1 gap-4 min-[1100px]:grid-cols-12">
          <div className={NGINX_SPAN.threeQuarter} data-nginx-width="3/4">
            <NginxChartCard
              anchor="nginx-status-dist"
              title="状态码分布"
              hint={NGINX_HINTS.statusDist}
              unit="次"
              items={statusBlocked ? [] : board.statusSteps}
              floor={1}
              kind="bar"
              countAxis
              formatReading={(value) => formatCount(value, '次')}
              phase={statusPhase}
              emptyText={emptyText}
              emptyDetail={statusBlocked ? SITE_EMPTY_DETAIL : undefined}
              onRetry={() => onRetry(NGINX_CARD_QUERIES.sitesStatus)}
            />
          </div>
          <div className={NGINX_SPAN.quarter} data-nginx-width="1/4">
            <NginxCompositionCard
              title="状态码构成"
              hint={NGINX_HINTS.statusMix}
              parts={statusParts}
              noun="次"
              phase={statusPhase}
              emptyText={emptyText}
              emptyDetail={statusBlocked ? SITE_EMPTY_DETAIL : undefined}
              onRetry={() => onRetry(NGINX_CARD_QUERIES.sitesStatus)}
            />
          </div>
        </div>
      </ProSection>
      <ProSection id="nginx-traffic-section" title="流量与处理">
        <div className="grid grid-cols-1 gap-4 min-[1100px]:grid-cols-12">
          <div className={NGINX_SPAN.half} data-nginx-width="1/2">
            <NginxChartCard
              title="入站与出站流量"
              hint={NGINX_HINTS.bytes}
              unit={scale.suffix}
              items={board.trafficSeries}
              floor={1}
              formatReading={(value) => formatBytesPerSecond(value, scale)}
              phase={trafficPhase}
              emptyText={emptyText}
              onRetry={() => onRetry(NGINX_CARD_QUERIES.sitesTraffic)}
            />
          </div>
          <div className={NGINX_SPAN.half} data-nginx-width="1/2">
            <NginxChartCard
              title="平均处理时间趋势"
              hint={NGINX_HINTS.avgTime}
              unit={durationUnitLabel(model.requestTimeUnit)}
              items={model.requestTimePoints.length ? [{
                id: 'star',
                label: '平均处理时间',
                color: '#2f6bff',
                points: model.requestTimePoints,
                reading: ''
              }] : []}
              floor={10}
              formatReading={(value) => formatDuration(value, model.requestTimeUnit)}
              phase={timePhase}
              emptyText={emptyText}
              onRetry={() => onRetry(NGINX_CARD_QUERIES.sitesTime)}
            />
          </div>
        </div>
      </ProSection>
      <ProSection id="nginx-sites-section" title="站点">
        <div className="grid grid-cols-1 gap-4 min-[1100px]:grid-cols-12">
          <div className={NGINX_SPAN.half} data-nginx-width="1/2">
            <NginxChartCard
              title="站点请求速率"
              hint={NGINX_HINTS.siteRate}
              unit="次/秒"
              items={trend}
              floor={1}
              formatReading={(value) => formatPerSecond(value, '次')}
              phase={rankPhase}
              emptyText={emptyText}
              emptyDetail={statusBlocked ? SITE_EMPTY_DETAIL : undefined}
              onRetry={() => onRetry(NGINX_CARD_QUERIES.sitesRank)}
            />
          </div>
          <div className={NGINX_SPAN.half} data-nginx-width="1/2">
            <NginxRankCard
              title="站点请求排行"
              hint={NGINX_HINTS.siteRank}
              rows={board.siteRank.map((row) => ({ id: row.zone, label: row.zone, value: row.count }))}
              selected={zone}
              onSelect={(id) => setZone((current) => (current === id ? null : id))}
              phase={rankPhase}
              emptyText={emptyText}
              emptyDetail={statusBlocked ? SITE_EMPTY_DETAIL : undefined}
              onRetry={() => onRetry(NGINX_CARD_QUERIES.sitesRank)}
              formatValue={(value) => formatCount(value, '次')}
            />
          </div>
        </div>
      </ProSection>
      <ProSection id="nginx-sites-table-section" title="站点明细">
        <div data-nginx-sites-table="">
          <ProMetricTable
          title="站点"
          hint={<NginxHint copy={NGINX_HINTS.sites} />}
          objectName="nginx"
          tabName="请求与站点"
          tableName="站点"
          columns={zoneColumns}
          rows={tablePhase === 'ready' ? zoneTableRows.map((row) => ({ ...row, key: row.key, cells: row.cells })) : []}
          footer={tablePhase === 'ready' ? zoneFooter : null}
          heightClass="h-[360px]"
          onSort={chooseSort}
          empty={tableEmpty}
        />
        </div>
      </ProSection>
      {model.showFilter ? (
        <ProSection id="nginx-filter-section" title="过滤器">
          <div data-nginx-filter-table="">
            <ProMetricTable
              title="过滤器"
              hint={<NginxHint copy={NGINX_HINTS.filter} />}
              objectName="nginx"
              tabName="请求与站点"
              tableName="过滤器"
              columns={filterColumns}
              rows={filterPhase === 'ready' ? filterTableRows : []}
              heightClass="h-[280px]"
              onSort={chooseFilterSort}
              empty={filterPhase !== 'ready' ? (
                <NginxChartCard title="" items={[]} floor={1} formatReading={() => ''} phase={filterPhase} emptyText={emptyText} onRetry={() => onRetry(NGINX_CARD_QUERIES.filterTable)} height={220} />
              ) : filterTableRows.length ? undefined : (
                <div className="flex flex-1 items-center justify-center text-[14px] text-[var(--color-text-3)]">{emptyText}</div>
              )}
            />
          </div>
        </ProSection>
      ) : null}
    </div>
  );
}

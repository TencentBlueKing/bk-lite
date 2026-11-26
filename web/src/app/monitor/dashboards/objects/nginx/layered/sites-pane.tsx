'use client';

import { useMemo, useState } from 'react';
import { byteScale, durationUnitLabel, formatBytes, formatBytesPerSecond, formatCount, formatDecimal, formatDuration, formatPerSecond, formatPercent, pickDurationUnit } from './format';
import { NGINX_HINTS } from './hints';
import { NginxChartCard, NginxRankCard, NginxRetryBanner, NginxTile } from './nginx-card';
import { NginxHint } from './nginx-hint';
import { filterPlotted } from './selection';
import type { NginxDashboardModel, ZoneTableRow } from './model';
import { NGINX_CARD_QUERIES, phaseOf, type NginxQueryPhase } from './query-phase';

const STATUS_COLORS: Record<string, string> = {
  '1xx': '#8c8c8c',
  '2xx': '#27c274',
  '3xx': '#2f6bff',
  '4xx': '#ff8a1f',
  '5xx': '#ff4d4f'
};

const numberCell = (value: number | null, text: string) => (value == null ? '--' : text);

function StatusMix({
  parts,
  phase,
  emptyText,
  onRetry
}: {
  parts: NginxDashboardModel['board']['statusParts'];
  phase: NginxQueryPhase;
  emptyText: string;
  onRetry: () => void;
}) {
  const known = parts.some((part) => part.count != null);
  if (phase !== 'ready' || !known) {
    return (
      <NginxChartCard
        title="状态码构成"
        hint={NGINX_HINTS.statusMix}
        items={[]}
        floor={1}
        formatReading={(value) => formatCount(value, '次')}
        phase={phase === 'ready' ? 'ready' : phase}
        emptyText={emptyText}
        onRetry={onRetry}
      />
    );
  }
  const rows = ['1xx', '2xx', '3xx', '4xx', '5xx'].map((code) => ({
    code,
    count: parts.find((part) => part.code === code)?.count ?? 0
  }));
  const total = rows.reduce((sum, row) => sum + row.count, 0);
  const peak = Math.max(...rows.map((row) => row.count), 0);
  return (
    <section className="flex h-[280px] flex-col rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-3">
      <div className="inline-flex items-center gap-1 text-[14px] font-semibold text-[var(--color-text-1)]">
        状态码构成
        <NginxHint copy={NGINX_HINTS.statusMix} />
      </div>
      <div className="mt-3 flex min-h-0 flex-1 flex-col justify-center gap-3">
        {rows.map((row) => {
          const share = total === 0 ? 0 : (row.count / total) * 100;
          const width = peak === 0 ? 0 : (row.count / peak) * 100;
          return (
            <div key={row.code} className="grid grid-cols-[48px_minmax(0,1fr)_auto] items-center gap-2 text-[13px]">
              <span>{row.code}</span>
              <span className="h-2 rounded-full bg-[var(--color-fill-2)]">
                <span className="block h-2 rounded-full" style={{ width: `${width}%`, background: STATUS_COLORS[row.code] }} />
              </span>
              <span className="tabular-nums text-[var(--color-text-1)]">{formatCount(row.count, '次')} · {formatDecimal(share)}%</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

type SortKey = 'rate' | 'window' | '1xx' | '2xx' | '3xx' | '4xx' | '5xx' | 'ratio' | 'in' | 'out' | 'time';

const sortValue = (row: ZoneTableRow, key: SortKey) => {
  if (key === 'rate') return row.requestRate;
  if (key === 'window') return row.windowRequests ?? null;
  if (key === 'in') return row.windowBytesIn ?? null;
  if (key === 'out') return row.windowBytesOut ?? null;
  if (key === 'time') return row.timeMs;
  if (key === 'ratio') {
    const total = row.windowRequests;
    const five = row.windowCodes?.['5xx'];
    if (total == null || total === 0 || five == null) return null;
    return five / total;
  }
  return row.windowCodes?.[key] ?? null;
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
  const [sortKey, setSortKey] = useState<SortKey>('rate');
  const [sortDesc, setSortDesc] = useState(true);
  const [zone, setZone] = useState<string | null>(null);
  const board = model.board;
  const kpiPhase = phaseOf(NGINX_CARD_QUERIES.sitesKpi, phases);
  const statusPhase = phaseOf(NGINX_CARD_QUERIES.sitesStatus, phases);
  const trafficPhase = phaseOf(NGINX_CARD_QUERIES.sitesTraffic, phases);
  const timePhase = phaseOf(NGINX_CARD_QUERIES.sitesTime, phases);
  const rankPhase = phaseOf(NGINX_CARD_QUERIES.sitesRank, phases);
  const tablePhase = phaseOf(NGINX_CARD_QUERIES.sitesTable, phases);
  const filterPhase = phaseOf(NGINX_CARD_QUERIES.filterTable, phases);
  const cardPhases = [kpiPhase, kpiPhase, kpiPhase, kpiPhase, statusPhase, statusPhase, trafficPhase, timePhase, rankPhase, rankPhase, tablePhase];
  if (model.showFilter) cardPhases.push(filterPhase);
  const failures = cardPhases.filter((item) => item === 'error').length;
  const rows = useMemo(() => [...model.zoneRows].sort((left, right) => {
    const delta = (sortValue(right, sortKey) ?? Number.NEGATIVE_INFINITY) - (sortValue(left, sortKey) ?? Number.NEGATIVE_INFINITY);
    return sortDesc ? delta : -delta;
  }), [model.zoneRows, sortDesc, sortKey]);
  const show1xx = [...rows, model.zoneSummary].some((row) => (row?.windowCodes?.['1xx'] ?? 0) > 0);
  const trend = zone ? filterPlotted(model.zoneRequest, new Set([zone])) : board.siteTrend;
  const bytePeak = board.trafficSeries.reduce((peak, item) => Math.max(peak, ...item.points.map((point) => Math.abs(point.value))), 0);
  const scale = byteScale(bytePeak);
  const chooseSort = (key: SortKey) => {
    if (sortKey === key) setSortDesc((value) => !value);
    else {
      setSortKey(key);
      setSortDesc(true);
    }
  };
  const head = (key: SortKey, label: string) => (
    <th className="px-2 py-2 text-right">
      <button type="button" className="font-semibold text-[var(--color-text-2)]" onClick={() => chooseSort(key)}>{label}</button>
    </th>
  );
  const tableTimeUnit = pickDurationUnit([
    ...model.zoneRows.map((row) => row.timeMs),
    model.zoneSummary?.timeMs
  ].reduce((peak, value) => (
    value != null && Number.isFinite(value) ? Math.max(peak, Math.abs(value)) : peak
  ), 0));
  const ratioOf = (row: ZoneTableRow) => {
    const total = row.windowRequests;
    const five = row.windowCodes?.['5xx'];
    if (total == null || total === 0 || five == null) return '--';
    return formatPercent(five / total);
  };

  return (
    <div className="flex flex-col gap-4" data-nginx-pane="sites">
      <NginxRetryBanner visible={failures >= 3} onRetry={onRetryFailed} />
      <div className="grid grid-cols-1 gap-4 min-[1100px]:grid-cols-12">
        <div className="min-[1100px]:col-span-3">
          <NginxTile label="窗口请求数" hint={NGINX_HINTS.windowRequests} unit="次" figure={board.windowRequests} phase={kpiPhase} emptyText={emptyText} onRetry={() => onRetry(NGINX_CARD_QUERIES.sitesKpi)} />
        </div>
        <div className="min-[1100px]:col-span-3">
          <NginxTile label="4xx 比例" hint={NGINX_HINTS.ratio4xx} figure={board.ratio4xx} sub={board.count4xx} phase={kpiPhase} emptyText={emptyText} onRetry={() => onRetry(NGINX_CARD_QUERIES.sitesKpi)} />
        </div>
        <div className="min-[1100px]:col-span-3">
          <NginxTile label="5xx 比例" hint={NGINX_HINTS.ratio5xx} figure={board.ratio5xx} sub={board.count5xx} tone={board.ratio5xxHot ? 'var(--color-fail)' : undefined} phase={kpiPhase} emptyText={emptyText} onRetry={() => onRetry(NGINX_CARD_QUERIES.sitesKpi)} />
        </div>
        <div className="min-[1100px]:col-span-3">
          <NginxTile label="平均处理时间" hint={NGINX_HINTS.avgTime} figure={board.avgTime} phase={kpiPhase} emptyText={emptyText} onRetry={() => onRetry(NGINX_CARD_QUERIES.sitesKpi)} />
        </div>
      </div>
      <div className="grid grid-cols-1 gap-4 min-[1100px]:grid-cols-2">
        <NginxChartCard
          anchor="nginx-status-dist"
          title="状态码分布"
          hint={NGINX_HINTS.statusDist}
          unit="次"
          items={board.statusSteps}
          floor={1}
          kind="bar"
          formatReading={(value) => formatCount(value, '次')}
          phase={statusPhase}
          emptyText={emptyText}
          onRetry={() => onRetry(NGINX_CARD_QUERIES.sitesStatus)}
        />
        <StatusMix parts={board.statusParts} phase={statusPhase} emptyText={emptyText} onRetry={() => onRetry(NGINX_CARD_QUERIES.sitesStatus)} />
      </div>
      <div className="grid grid-cols-1 gap-4 min-[1100px]:grid-cols-2">
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
        <NginxChartCard
          title="平均处理时间"
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
      <div className="grid grid-cols-1 gap-4 min-[1100px]:grid-cols-2">
        <NginxChartCard
          title="站点请求速率"
          hint={NGINX_HINTS.siteRate}
          unit="次/秒"
          items={trend}
          floor={1}
          formatReading={(value) => formatPerSecond(value, '次')}
          phase={rankPhase}
          emptyText={emptyText}
          onRetry={() => onRetry(NGINX_CARD_QUERIES.sitesRank)}
        />
        <NginxRankCard
          title="站点请求排行"
          hint={NGINX_HINTS.siteRank}
          rows={board.siteRank.map((row) => ({ id: row.zone, label: row.zone, value: row.count }))}
          selected={zone}
          onSelect={(id) => setZone((current) => (current === id ? null : id))}
          phase={rankPhase}
          emptyText={emptyText}
          onRetry={() => onRetry(NGINX_CARD_QUERIES.sitesRank)}
          formatValue={(value) => formatCount(value, '次')}
        />
      </div>
      <section className="flex h-[360px] flex-col overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)]" data-nginx-sites-table="">
        <div className="flex items-center gap-1 px-3 pt-3 text-[14px] font-semibold text-[var(--color-text-1)]">
          站点
          <NginxHint copy={NGINX_HINTS.sites} />
        </div>
        {tablePhase !== 'ready' ? (
          <div className="min-h-0 flex-1">
            <NginxChartCard title="" items={[]} floor={1} formatReading={() => ''} phase={tablePhase} emptyText={emptyText} onRetry={() => onRetry(NGINX_CARD_QUERIES.sitesTable)} height={300} />
          </div>
        ) : (
          <div className="min-h-0 flex-1 overflow-auto">
            <table className="w-full border-separate border-spacing-0 text-[13px]">
              <thead className="sticky top-0 bg-[var(--color-bg)]">
                <tr>
                  <th className="min-w-[160px] px-2 py-2 text-left">站点</th>
                  {head('rate', '请求速率')}
                  {head('window', '窗口请求数')}
                  {show1xx ? head('1xx', '1xx') : null}
                  {head('2xx', '2xx')}
                  {head('3xx', '3xx')}
                  {head('4xx', '4xx')}
                  {head('5xx', '5xx')}
                  {head('ratio', '5xx 比例')}
                  {head('in', '入站')}
                  {head('out', '出站')}
                  {head('time', '平均处理时间')}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.zone} data-nginx-zone-row={row.zone}>
                    <td className="max-w-[240px] truncate px-2 py-2 text-left" title={row.zone}>{row.zone}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{numberCell(row.requestRate, formatPerSecond(row.requestRate ?? 0, '次'))}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{numberCell(row.windowRequests ?? null, formatCount(row.windowRequests ?? 0, '次'))}</td>
                    {show1xx ? <td className="px-2 py-2 text-right tabular-nums">{numberCell(row.windowCodes?.['1xx'] ?? null, formatCount(row.windowCodes?.['1xx'] ?? 0, '次'))}</td> : null}
                    {(['2xx', '3xx', '4xx', '5xx'] as const).map((code) => (
                      <td key={code} className="px-2 py-2 text-right tabular-nums">{numberCell(row.windowCodes?.[code] ?? null, formatCount(row.windowCodes?.[code] ?? 0, '次'))}</td>
                    ))}
                    <td className="px-2 py-2 text-right tabular-nums">{ratioOf(row)}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{numberCell(row.windowBytesIn ?? null, formatBytes(row.windowBytesIn ?? 0))}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{numberCell(row.windowBytesOut ?? null, formatBytes(row.windowBytesOut ?? 0))}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{numberCell(row.timeMs, formatDuration(row.timeMs ?? 0, tableTimeUnit))}</td>
                  </tr>
                ))}
              </tbody>
              {model.zoneSummary ? (
                <tfoot className="sticky bottom-0 bg-[var(--color-fill-1)] font-semibold">
                  <tr data-nginx-zone-row="total">
                    <td className="px-2 py-2 text-left">全部站点</td>
                    <td className="px-2 py-2 text-right tabular-nums">{numberCell(model.zoneSummary.requestRate, formatPerSecond(model.zoneSummary.requestRate ?? 0, '次'))}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{numberCell(model.zoneSummary.windowRequests ?? null, formatCount(model.zoneSummary.windowRequests ?? 0, '次'))}</td>
                    {show1xx ? <td className="px-2 py-2 text-right tabular-nums">{numberCell(model.zoneSummary.windowCodes?.['1xx'] ?? null, formatCount(model.zoneSummary.windowCodes?.['1xx'] ?? 0, '次'))}</td> : null}
                    {(['2xx', '3xx', '4xx', '5xx'] as const).map((code) => (
                      <td key={code} className="px-2 py-2 text-right tabular-nums">{numberCell(model.zoneSummary?.windowCodes?.[code] ?? null, formatCount(model.zoneSummary?.windowCodes?.[code] ?? 0, '次'))}</td>
                    ))}
                    <td className="px-2 py-2 text-right tabular-nums">{ratioOf(model.zoneSummary)}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{numberCell(model.zoneSummary.windowBytesIn ?? null, formatBytes(model.zoneSummary.windowBytesIn ?? 0))}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{numberCell(model.zoneSummary.windowBytesOut ?? null, formatBytes(model.zoneSummary.windowBytesOut ?? 0))}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{numberCell(model.zoneSummary.timeMs, formatDuration(model.zoneSummary.timeMs ?? 0, tableTimeUnit))}</td>
                  </tr>
                </tfoot>
              ) : null}
            </table>
          </div>
        )}
      </section>
      {model.showFilter ? (
        <section className="flex h-[280px] flex-col overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)]" data-nginx-filter-table="">
          <div className="flex items-center gap-1 px-3 pt-3 text-[14px] font-semibold text-[var(--color-text-1)]">
            过滤器
            <NginxHint copy={NGINX_HINTS.filter} />
          </div>
          {filterPhase !== 'ready' ? (
            <NginxChartCard title="" items={[]} floor={1} formatReading={() => ''} phase={filterPhase} emptyText={emptyText} onRetry={() => onRetry(NGINX_CARD_QUERIES.filterTable)} height={220} />
          ) : (
            <div className="min-h-0 flex-1 overflow-auto">
              <table className="w-full text-[13px]">
                <thead className="sticky top-0 bg-[var(--color-bg)] text-[var(--color-text-2)]">
                  <tr>
                    <th className="min-w-[160px] px-2 py-2 text-left">过滤器</th>
                    <th className="px-2 py-2 text-left">过滤键</th>
                    <th className="px-2 py-2 text-right">请求速率</th>
                    <th className="px-2 py-2 text-right">窗口请求数</th>
                    <th className="px-2 py-2 text-right">2xx</th>
                    <th className="px-2 py-2 text-right">4xx</th>
                    <th className="px-2 py-2 text-right">5xx</th>
                    <th className="px-2 py-2 text-right">入站</th>
                    <th className="px-2 py-2 text-right">出站</th>
                    <th className="px-2 py-2 text-right">平均处理时间</th>
                  </tr>
                </thead>
                <tbody>
                  {model.filterRows.map((row) => (
                    <tr key={`${row.filterName}|${row.filterKey}`}>
                      <td className="max-w-[220px] truncate px-2 py-2" title={row.filterName}>{row.filterName}</td>
                      <td className="px-2 py-2">{row.filterKey || '--'}</td>
                      <td className="px-2 py-2 text-right tabular-nums">{numberCell(row.requestRate, formatPerSecond(row.requestRate ?? 0, '次'))}</td>
                      <td className="px-2 py-2 text-right tabular-nums">{numberCell(row.windowRequests ?? null, formatCount(row.windowRequests ?? 0, '次'))}</td>
                      {(['2xx', '4xx', '5xx'] as const).map((code) => (
                        <td key={code} className="px-2 py-2 text-right tabular-nums">{numberCell(row.windowCodes?.[code] ?? null, formatCount(row.windowCodes?.[code] ?? 0, '次'))}</td>
                      ))}
                      <td className="px-2 py-2 text-right tabular-nums">{numberCell(row.windowBytesIn ?? null, formatBytes(row.windowBytesIn ?? 0))}</td>
                      <td className="px-2 py-2 text-right tabular-nums">{numberCell(row.windowBytesOut ?? null, formatBytes(row.windowBytesOut ?? 0))}</td>
                      <td className="px-2 py-2 text-right tabular-nums">{numberCell(row.timeMs, formatDuration(row.timeMs ?? 0, model.zoneTimeUnit))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      ) : null}
    </div>
  );
}

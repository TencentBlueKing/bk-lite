'use client';

import { useMemo, useState } from 'react';
import { ProSection } from '../../host/layered/pro-chrome';
import { formatBytesPerSecond, formatDuration, formatPerSecond } from './format';
import { NGINX_HINTS } from './hints';
import { NginxDimensionalChart } from './dimensional-chart';
import { NginxHint } from './nginx-hint';
import { zoneColumns, zoneTableLabel, type NginxDashboardModel, type ZoneTableRow } from './model';

const cell = (value: number | null, text: string) => (value == null ? '--' : text);

export default function SitesPane({
  model,
  loading,
  emptyText
}: {
  model: NginxDashboardModel;
  loading: boolean;
  emptyText: string;
}) {
  const [sortKey, setSortKey] = useState<'rate' | '5xx'>('rate');
  const scale = { div: model.byteScaleDiv, suffix: model.byteSuffix };
  const rows = useMemo(() => {
    const copy = [...model.zoneRows];
    copy.sort((left, right) => {
      const primary = sortKey === '5xx'
        ? (right.codes['5xx'] ?? Number.NEGATIVE_INFINITY) - (left.codes['5xx'] ?? Number.NEGATIVE_INFINITY)
        : (right.requestRate ?? Number.NEGATIVE_INFINITY) - (left.requestRate ?? Number.NEGATIVE_INFINITY);
      return primary;
    });
    return copy;
  }, [model.zoneRows, sortKey]);
  const columns = zoneColumns(model.zoneSummary ? [...rows, model.zoneSummary] : rows);
  const filterHas = (pick: (row: NginxDashboardModel['filterRows'][number]) => number | null) => (
    model.filterRows.some((row) => {
      const value = pick(row);
      return value != null && Number.isFinite(value);
    })
  );
  const filterColumns = {
    request: filterHas((row) => row.requestRate),
    c2: filterHas((row) => row.codes['2xx']),
    c4: filterHas((row) => row.codes['4xx']),
    c5: filterHas((row) => row.codes['5xx']),
    c1: filterHas((row) => row.codes['1xx']),
    c3: filterHas((row) => row.codes['3xx']),
    bytesIn: filterHas((row) => row.bytesIn),
    bytesOut: filterHas((row) => row.bytesOut),
    time: filterHas((row) => row.timeMs)
  };
  const filterColSpan = 2 + Object.values(filterColumns).filter(Boolean).length;
  const siteColSpan = 1
    + Number(columns.request)
    + Number(columns.c1)
    + Number(columns.c2)
    + Number(columns.c3)
    + Number(columns.c4)
    + Number(columns.c5)
    + Number(columns.bytesIn)
    + Number(columns.bytesOut)
    + Number(columns.time);
  const rateText = (value: number | null) => cell(value, formatPerSecond(value ?? 0, '次'));
  const byteText = (value: number | null) => cell(value, formatBytesPerSecond(value ?? 0, scale));
  const timeText = (value: number | null) => cell(value, formatDuration(value ?? 0, model.zoneTimeUnit));
  const renderRow = (row: ZoneTableRow, summary = false) => (
    <tr key={`${summary ? 'sum' : 'zone'}-${row.zone}`} data-nginx-zone-row={summary ? 'total' : row.zone} className={summary ? 'bg-[var(--color-fill-1)]' : undefined}>
      <td className="px-2 py-2 font-medium text-[var(--color-text-1)]">{zoneTableLabel(row.zone, summary)}</td>
      {columns.request ? <td className="px-2 py-2 tabular-nums">{rateText(row.requestRate)}</td> : null}
      {columns.c2 ? <td className="px-2 py-2 tabular-nums">{rateText(row.codes['2xx'])}</td> : null}
      {columns.c4 ? <td className="px-2 py-2 tabular-nums">{rateText(row.codes['4xx'])}</td> : null}
      {columns.c5 ? <td className="px-2 py-2 tabular-nums">{rateText(row.codes['5xx'])}</td> : null}
      {columns.c1 ? <td className="px-2 py-2 tabular-nums">{rateText(row.codes['1xx'])}</td> : null}
      {columns.c3 ? <td className="px-2 py-2 tabular-nums">{rateText(row.codes['3xx'])}</td> : null}
      {columns.bytesIn ? <td className="px-2 py-2 tabular-nums">{byteText(row.bytesIn)}</td> : null}
      {columns.bytesOut ? <td className="px-2 py-2 tabular-nums">{byteText(row.bytesOut)}</td> : null}
      {columns.time ? <td className="px-2 py-2 tabular-nums">{timeText(row.timeMs)}</td> : null}
    </tr>
  );

  return (
    <div className="flex flex-col gap-4" data-nginx-pane="sites">
      <NginxDimensionalChart
        title="各站点请求速率"
        hint={NGINX_HINTS.request}
        items={model.zoneRequest}
        floor={1}
        formatReading={(value) => formatPerSecond(value, '次')}
        loading={loading}
        emptyText={emptyText}
      />
      <NginxDimensionalChart
        title="状态码"
        hint={NGINX_HINTS.codes}
        items={model.zoneStatus}
        floor={1}
        stack
        formatReading={(value) => formatPerSecond(value, '次')}
        loading={loading}
        emptyText={emptyText}
      />
      <NginxDimensionalChart
        title="入站与出站"
        hint={NGINX_HINTS.bytes}
        items={model.zoneBytes}
        floor={1}
        formatReading={(value) => formatBytesPerSecond(value, scale)}
        loading={loading}
        emptyText={emptyText}
      />
      <NginxDimensionalChart
        title="平均处理时间"
        hint={NGINX_HINTS.zoneTime}
        items={model.zoneTime}
        floor={10}
        formatReading={(value) => formatDuration(value, model.zoneTimeUnit)}
        loading={loading}
        emptyText={emptyText}
      />
      <ProSection title="站点" hint={<NginxHint copy={NGINX_HINTS.request} />}>
        <div className="mb-2 flex justify-end">
          <label className="inline-flex items-center gap-2 text-[12px] text-[var(--color-text-2)]">
            排序
            <select
              className="rounded border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1 text-[12px] text-[var(--color-text-1)]"
              value={sortKey}
              onChange={(event) => setSortKey(event.target.value === '5xx' ? '5xx' : 'rate')}
            >
              <option value="rate">请求速率</option>
              <option value="5xx">5xx</option>
            </select>
          </label>
        </div>
        <div className="overflow-x-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)]">
          <table className="w-full border-collapse text-left text-[13px]">
            <thead>
              <tr className="border-b border-[var(--color-border)] text-[var(--color-text-3)]">
                <th className="px-2 py-2 font-semibold">站点</th>
                {columns.request ? <th className="px-2 py-2 font-semibold">请求速率</th> : null}
                {columns.c2 ? <th className="px-2 py-2 font-semibold">2xx</th> : null}
                {columns.c4 ? <th className="px-2 py-2 font-semibold">4xx</th> : null}
                {columns.c5 ? <th className="px-2 py-2 font-semibold">5xx</th> : null}
                {columns.c1 ? <th className="px-2 py-2 font-semibold">1xx</th> : null}
                {columns.c3 ? <th className="px-2 py-2 font-semibold">3xx</th> : null}
                {columns.bytesIn ? <th className="px-2 py-2 font-semibold">入站速率</th> : null}
                {columns.bytesOut ? <th className="px-2 py-2 font-semibold">出站速率</th> : null}
                {columns.time ? <th className="px-2 py-2 font-semibold">平均处理时间</th> : null}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => renderRow(row))}
              {model.zoneSummary ? renderRow(model.zoneSummary, true) : null}
              {!rows.length && !model.zoneSummary ? (
                <tr>
                  <td className="px-2 py-6 text-center font-semibold text-[var(--color-text-2)]" colSpan={siteColSpan}>{emptyText}</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </ProSection>
      {model.showFilter ? (
        <ProSection title="过滤器" hint={<NginxHint copy={NGINX_HINTS.filter} />}>
          <NginxDimensionalChart
            title="过滤器请求速率"
            hint={NGINX_HINTS.filter}
            items={model.filterRequest}
            floor={1}
            formatReading={(value) => formatPerSecond(value, '次')}
            loading={loading}
            emptyText={emptyText}
          />
          <div className="overflow-x-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)]">
            <table className="w-full border-collapse text-left text-[13px]">
              <thead>
                <tr className="border-b border-[var(--color-border)] text-[var(--color-text-3)]">
                  <th className="px-2 py-2 font-semibold">过滤器</th>
                  <th className="px-2 py-2 font-semibold">过滤键</th>
                  {filterColumns.request ? <th className="px-2 py-2 font-semibold">请求速率</th> : null}
                  {filterColumns.c2 ? <th className="px-2 py-2 font-semibold">2xx</th> : null}
                  {filterColumns.c4 ? <th className="px-2 py-2 font-semibold">4xx</th> : null}
                  {filterColumns.c5 ? <th className="px-2 py-2 font-semibold">5xx</th> : null}
                  {filterColumns.c1 ? <th className="px-2 py-2 font-semibold">1xx</th> : null}
                  {filterColumns.c3 ? <th className="px-2 py-2 font-semibold">3xx</th> : null}
                  {filterColumns.bytesIn ? <th className="px-2 py-2 font-semibold">入站速率</th> : null}
                  {filterColumns.bytesOut ? <th className="px-2 py-2 font-semibold">出站速率</th> : null}
                  {filterColumns.time ? <th className="px-2 py-2 font-semibold">平均处理时间</th> : null}
                </tr>
              </thead>
              <tbody>
                {model.filterRows.map((row) => (
                  <tr key={`${row.filterName}|${row.filterKey}`} data-nginx-filter-key={row.filterKey}>
                    <td className="px-2 py-2">{row.filterName || '--'}</td>
                    <td className="px-2 py-2">{row.filterKey || '--'}</td>
                    {filterColumns.request ? <td className="px-2 py-2 tabular-nums">{rateText(row.requestRate)}</td> : null}
                    {filterColumns.c2 ? <td className="px-2 py-2 tabular-nums">{rateText(row.codes['2xx'])}</td> : null}
                    {filterColumns.c4 ? <td className="px-2 py-2 tabular-nums">{rateText(row.codes['4xx'])}</td> : null}
                    {filterColumns.c5 ? <td className="px-2 py-2 tabular-nums">{rateText(row.codes['5xx'])}</td> : null}
                    {filterColumns.c1 ? <td className="px-2 py-2 tabular-nums">{rateText(row.codes['1xx'])}</td> : null}
                    {filterColumns.c3 ? <td className="px-2 py-2 tabular-nums">{rateText(row.codes['3xx'])}</td> : null}
                    {filterColumns.bytesIn ? <td className="px-2 py-2 tabular-nums">{byteText(row.bytesIn)}</td> : null}
                    {filterColumns.bytesOut ? <td className="px-2 py-2 tabular-nums">{byteText(row.bytesOut)}</td> : null}
                    {filterColumns.time ? <td className="px-2 py-2 tabular-nums">{timeText(row.timeMs)}</td> : null}
                  </tr>
                ))}
                {!model.filterRows.length ? (
                  <tr>
                    <td className="px-2 py-6 text-center font-semibold text-[var(--color-text-2)]" colSpan={filterColSpan}>{emptyText}</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </ProSection>
      ) : null}
    </div>
  );
}

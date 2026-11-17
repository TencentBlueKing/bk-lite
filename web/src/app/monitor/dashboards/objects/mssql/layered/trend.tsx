'use client';

import { useMemo } from 'react';
import type { ChartData } from '@/app/monitor/types';
import type { MetricUnit } from '../../../shared/types';
import { ThinTimeSeries } from '../../host/layered/pro-chrome';
import { seriesSampleValues } from '../../host/layered/focus-axis';
import { MSSQL_CLERK_LIST_MAX_PX, MSSQL_LIST_ROW_PX, mssqlLockedReading } from './display-units';
import { MssqlHint } from './hint';
import {
  joinMetric,
  mssqlCountAxisBounds,
  mssqlCountMerged,
  mssqlLatest,
  mssqlMerged,
  mssqlSamplesAreFlatZero,
  type MssqlMetricMap
} from './series';
import { mssqlDeferEmpty } from './card-face';

export interface MssqlSeriesSpec {
  name: string;
  label: string;
  color: string;
  unit: MetricUnit;
  dashed?: boolean;
}

export function MssqlSeriesReadout({
  items
}: {
  items: ReadonlyArray<{ label: string; color: string; reading?: string; dashed?: boolean }>;
}) {
  if (!items.length) return null;
  return (
    <ul
      className="m-0 mt-2 flex w-full list-none flex-col overflow-y-auto border-t border-[var(--color-border)] p-0"
      style={{ maxHeight: MSSQL_CLERK_LIST_MAX_PX }}
      data-mssql-series-readout="rows"
    >
      {items.map((item) => (
        <li
          key={item.label}
          className="flex w-full min-w-0 items-center justify-between gap-3 border-b border-[var(--color-border)] px-1 text-[13px]"
          style={{ height: MSSQL_LIST_ROW_PX }}
        >
          <span className="min-w-0 flex-1 truncate text-[var(--color-text-1)]">{item.label}</span>
          <span className="shrink-0 text-right font-semibold tabular-nums text-[var(--color-text-1)]">
            {item.reading || '—'}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function MssqlTrend({
  anchor,
  title,
  body,
  series,
  metricMap,
  pending,
  percent = false,
  counts = false,
  dualAxis = false,
  data,
  loading = false,
  batchLoading = false,
  plotHeight
}: {
  anchor: string;
  title: string;
  body: string;
  series: readonly MssqlSeriesSpec[];
  metricMap: MssqlMetricMap;
  pending: ReadonlySet<string>;
  percent?: boolean;
  counts?: boolean;
  /** 单位相同但量级差得大时也分轴，避免一条线把另一条压扁。 */
  dualAxis?: boolean;
  data?: ChartData[];
  /** 本卡相关查询仍在进行，且还没有点时只显示加载中。 */
  loading?: boolean;
  /** 同一批指标还没全部返回。没有点的卡先保持加载中。 */
  batchLoading?: boolean;
  /** 图区高度。用来和旁边按行固定的列表对齐。 */
  plotHeight?: number;
}) {
  const items = series.map((item) => ({ name: item.name, label: item.label }));
  const plotted = data ?? (counts ? mssqlCountMerged(metricMap, items) : mssqlMerged(metricMap, items));
  const mixedUnits = new Set(series.map((item) => item.unit)).size > 1 || dualAxis;
  const multi = series.length > 1;
  const awaiting = mssqlDeferEmpty(
    plotted.length > 0,
    loading || series.some((item) => pending.has(item.name)),
    batchLoading
  );
  const samples = seriesSampleValues(plotted);
  const peak = samples.reduce((max, value) => Math.max(max, Math.abs(value)), 0);
  const unit = series[0]?.unit;
  const uniform = series.every((item) => item.unit === unit);
  const formatReading = useMemo(
    () => (uniform ? mssqlLockedReading(unit, peak) : null),
    [peak, uniform, unit]
  );
  const countBounds = counts ? mssqlCountAxisBounds(samples) : null;
  const percentZero = Boolean(percent && series.some((_, index) => {
    const key = `value${index + 1}`;
    const values = plotted.flatMap((point) => {
      const value = point[key];
      return typeof value === 'number' && Number.isFinite(value) ? [value] : [];
    });
    return mssqlSamplesAreFlatZero(values);
  }));
  const legends = series.map((item) => {
    const latest = mssqlLatest(metricMap, item.name);
    return {
      label: item.label,
      color: item.color,
      dashed: item.dashed,
      unit: mixedUnits ? item.unit : undefined,
      reading: multi && latest != null
        ? (formatReading ? formatReading(latest) : joinMetric(latest, item.unit))
        : undefined
    };
  });
  return (
    <div
      id={`mssql-${anchor}`}
      className="min-w-0 scroll-mt-3"
      data-mssql-chart={anchor}
      data-mssql-face={awaiting ? 'loading' : plotted.length > 0 ? 'ready' : 'empty'}
    >
      <ThinTimeSeries
        title={title}
        hintNode={<MssqlHint kind={`mssql-${anchor}`} title={title} body={body} />}
        unit={series[0]?.unit || 'none'}
        valueBounds={percent ? { min: 0, max: 100 } : undefined}
        resolveValueBounds={countBounds ? () => countBounds : undefined}
        pinAxisZero={!percent}
        independentAxes={mixedUnits}
        keepLegend={multi}
        markZeroCount={Boolean((counts && countBounds) || percentZero)}
        keepSeriesColor={Boolean((counts && countBounds) || percentZero)}
        loading={awaiting}
        emptyText="本窗口暂无数据"
        data={plotted}
        legends={legends}
        formatReading={formatReading ?? undefined}
        plotHeight={plotHeight}
      />
    </div>
  );
}

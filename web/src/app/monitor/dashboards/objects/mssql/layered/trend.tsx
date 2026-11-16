'use client';

import type { ChartData } from '@/app/monitor/types';
import type { MetricUnit } from '../../../shared/types';
import { ThinTimeSeries } from '../../host/layered/pro-chrome';
import { seriesSampleValues } from '../../host/layered/focus-axis';
import { MssqlHint } from './hint';
import {
  joinMetric,
  mssqlCountAxisBounds,
  mssqlCountMerged,
  mssqlLatest,
  mssqlMerged,
  type MssqlMetricMap
} from './series';

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
    <ul className="m-0 mt-2 flex list-none flex-wrap gap-x-4 gap-y-1 p-0" data-mssql-series-readout="">
      {items.map((item) => (
        <li
          key={item.label}
          className="inline-flex min-w-0 items-baseline gap-1.5 text-[12px] leading-5 text-[var(--color-text-3)]"
        >
          <span
            aria-hidden
            className="inline-block shrink-0 self-center"
            style={item.dashed
              ? {
                width: 14,
                height: 0,
                borderTop: `1.5px dashed ${item.color}`,
                background: 'transparent'
              }
              : {
                width: 8,
                height: 8,
                borderRadius: 999,
                background: item.color
              }}
          />
          <span className="min-w-0 truncate">{item.label}</span>
          <span className="shrink-0 font-semibold tabular-nums" style={{ color: item.color }}>
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
  data
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
}) {
  const items = series.map((item) => ({ name: item.name, label: item.label }));
  const plotted = data ?? (counts ? mssqlCountMerged(metricMap, items) : mssqlMerged(metricMap, items));
  const mixedUnits = new Set(series.map((item) => item.unit)).size > 1 || dualAxis;
  const multi = series.length > 1;
  const awaiting = series.some((item) => pending.has(item.name)) && plotted.length === 0;
  const samples = seriesSampleValues(plotted);
  const countBounds = counts ? mssqlCountAxisBounds(samples) : null;
  const legends = series.map((item) => {
    const latest = mssqlLatest(metricMap, item.name);
    return {
      label: item.label,
      color: item.color,
      dashed: item.dashed,
      unit: mixedUnits ? item.unit : undefined,
      reading: multi && latest != null ? joinMetric(latest, item.unit) : undefined
    };
  });
  return (
    <div id={`mssql-${anchor}`} className="min-w-0 scroll-mt-3" data-mssql-chart={anchor}>
      <ThinTimeSeries
        title={title}
        hintNode={<MssqlHint kind={`mssql-${anchor}`} title={title} body={body} />}
        unit={series[0]?.unit || 'none'}
        valueBounds={percent ? { min: 0, max: 100 } : undefined}
        resolveValueBounds={countBounds ? () => countBounds : undefined}
        pinAxisZero={!percent}
        independentAxes={mixedUnits}
        keepLegend={multi}
        markZeroCount={Boolean(counts && countBounds)}
        keepSeriesColor={Boolean(counts && countBounds)}
        loading={awaiting}
        emptyText="本窗口暂无数据"
        data={plotted}
        legends={legends}
      />
    </div>
  );
}

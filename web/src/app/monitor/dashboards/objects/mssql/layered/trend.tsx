'use client';

import { cloneElement, isValidElement, useMemo, useState, type ReactElement } from 'react';
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

interface ReadoutItem {
  label: string;
  color: string;
  reading?: string;
  dashed?: boolean;
}

interface SideChartProps {
  data?: ChartData[];
  legends?: ReadonlyArray<ReadoutItem>;
}

/** 选中的维度留在折线上。一个都没选时仍画全部，避免空图。 */
function projectSideSeries(
  data: ChartData[],
  legends: ReadonlyArray<ReadoutItem>,
  selected: ReadonlySet<string>
) {
  if (selected.size === 0) return { data, legends };
  const kept = legends
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => selected.has(item.label));
  if (!kept.length) return { data, legends };
  const nextLegends = kept.map(({ item }) => item);
  const nextData = data.map((point) => {
    const next: ChartData = { time: point.time };
    if (point.gapIntervals) next.gapIntervals = point.gapIntervals;
    kept.forEach(({ index }, target) => {
      const from = `value${index + 1}`;
      const to = `value${target + 1}`;
      next[to] = point[from];
      const detail = point.details?.[from];
      if (detail) {
        next.details = next.details || {};
        next.details[to] = detail;
      }
      const metric = point.seriesMetrics?.[from];
      if (metric) {
        next.seriesMetrics = next.seriesMetrics || {};
        next.seriesMetrics[to] = metric;
      }
    });
    return next;
  });
  return { data: nextData, legends: nextLegends };
}

export function MssqlSeriesReadout({
  items,
  fill = false,
  selected,
  onToggle
}: {
  items: ReadonlyArray<ReadoutItem>;
  /** 跟左侧折线卡齐高，多出来的行在栏内滚动。 */
  fill?: boolean;
  selected?: ReadonlySet<string>;
  onToggle?: (label: string) => void;
}) {
  if (!items.length) return null;
  return (
    <ul
      className={`m-0 flex w-full list-none flex-col overflow-y-auto bg-[var(--color-bg)] p-0 ${fill ? 'h-full' : ''}`}
      style={fill ? undefined : { maxHeight: MSSQL_CLERK_LIST_MAX_PX }}
      data-mssql-series-readout="rows"
    >
      {items.map((item) => {
        const on = Boolean(selected?.has(item.label));
        return (
          <li
            key={item.label}
            className="border-b border-solid border-[var(--color-border)] last:border-b-0"
            style={{ height: MSSQL_LIST_ROW_PX }}
          >
            <button
              type="button"
              aria-pressed={on}
              data-mssql-readout-selected={on ? 'true' : 'false'}
              className={`flex h-full w-full min-w-0 cursor-pointer items-center justify-between gap-2 border-0 px-2 text-left text-[13px] ${on ? 'bg-[var(--color-fill-1)]' : 'bg-[var(--color-bg)]'}`}
              onClick={() => onToggle?.(item.label)}
            >
              <span className="flex min-w-0 flex-1 items-center gap-2">
                <span
                  aria-hidden
                  data-mssql-readout-check=""
                  className="inline-flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-[3px] border text-[10px] leading-none"
                  style={{
                    borderColor: item.color,
                    background: on ? item.color : 'transparent',
                    color: 'var(--color-bg)'
                  }}
                >
                  {on ? '✓' : ''}
                </span>
                <span
                  aria-hidden
                  data-mssql-readout-swatch=""
                  className="inline-block h-2 w-2 shrink-0 rounded-full"
                  style={{ background: item.color }}
                />
                <span className="min-w-0 truncate text-[var(--color-text-1)]" title={item.label}>{item.label}</span>
              </span>
              <span
                data-mssql-readout-value=""
                className="shrink-0 text-right font-semibold tabular-nums"
                style={{ color: item.color }}
              >
                {item.reading || '—'}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

/** 方案 A：左折线约占 3/4，右读数栏约占 1/4。点行多选，只改左侧折线。 */
export function MssqlSideReadout({
  chart,
  items
}: {
  chart: ReactElement<SideChartProps>;
  items: ReadonlyArray<ReadoutItem>;
}) {
  const [selected, setSelected] = useState<ReadonlySet<string>>(() => new Set());
  if (!items.length) return <>{chart}</>;
  const visible = isValidElement(chart)
    ? projectSideSeries(chart.props.data || [], chart.props.legends || items, selected)
    : null;
  const plotted = visible && isValidElement(chart)
    ? cloneElement(chart, { data: visible.data, legends: visible.legends })
    : chart;
  const toggle = (label: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  };
  return (
    <div
      className="grid grid-cols-1 items-stretch gap-4 min-[900px]:grid-cols-[minmax(0,3fr)_minmax(0,1fr)]"
      data-mssql-side-readout=""
    >
      <div className="min-w-0">{plotted}</div>
      <div className="relative min-h-0">
        <div
          className="overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] max-[899px]:max-h-[216px] min-[900px]:absolute min-[900px]:inset-0"
          data-mssql-series-frame=""
        >
          <MssqlSeriesReadout items={items} fill selected={selected} onToggle={toggle} />
        </div>
      </div>
    </div>
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
  holdSeriesColor = false,
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
  /** 贴在共用轴底部的序列仍用自己的颜色，不另开右轴。 */
  holdSeriesColor?: boolean;
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
  const mixedUnits = new Set(series.map((item) => item.unit)).size > 1;
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
      data-mssql-axes={mixedUnits ? 'dual' : 'shared'}
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
        keepSeriesColor={Boolean((counts && countBounds) || percentZero || holdSeriesColor)}
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

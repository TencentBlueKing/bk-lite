'use client';

import { useState } from 'react';
import { CHART_COLORS } from '@/app/monitor/constants';
import type { ChartData } from '@/app/monitor/types';
import type { MetricUnit } from '../../../shared/types';
import { ThinTimeSeries } from '../../host/layered/pro-chrome';
import { FLAT_ZERO_STROKE_LIFT_PX } from '../../host/layered/flat-zero-stroke';
import { DOCKER_BLANK, dimensionUsesSideReadout, plottedDimensionNames } from './reading';
import type { DimensionSeries } from './view';

interface DimensionChartProps {
  chartKey: string;
  title: string;
  hint: string;
  unit: MetricUnit;
  formatReading: (value: number) => string;
  series: readonly DimensionSeries[];
  emptyText: string;
  clearLabel: string;
}

const chartData = (series: readonly DimensionSeries[]): ChartData[] => {
  const byTime = new Map<number, ChartData>();
  series.forEach((item, index) => {
    const key = `value${index + 1}`;
    item.points.forEach((point) => {
      const row = byTime.get(point.time) ?? { time: point.time };
      row[key] = point.value;
      byTime.set(point.time, row);
    });
  });
  return Array.from(byTime.values()).sort((left, right) => left.time - right.time);
};

export default function DockerDimensionChart({
  chartKey,
  title,
  hint,
  unit,
  formatReading,
  series,
  emptyText,
  clearLabel
}: DimensionChartProps) {
  const [selected, setSelected] = useState<ReadonlySet<string>>(() => new Set());
  const names = series.map((item) => item.name);
  const liveSelected = new Set(Array.from(selected).filter((name) => names.includes(name)));
  if (liveSelected.size !== selected.size) setSelected(liveSelected);
  const side = dimensionUsesSideReadout(series.length);
  const plottedNames = plottedDimensionNames(names, liveSelected);
  const plotted = series.filter((item) => plottedNames.includes(item.name));
  const colorOf = (name: string) => {
    const index = Math.max(names.indexOf(name), 0);
    return CHART_COLORS[index % CHART_COLORS.length];
  };
  const chart = (
    <ThinTimeSeries
      title={title}
      hint={hint}
      unit={unit}
      pinAxisZero
      flatZeroStrokeLiftPx={FLAT_ZERO_STROKE_LIFT_PX}
      hideLegend={side}
      formatReading={formatReading}
      emptyText={emptyText}
      data={chartData(plotted)}
      legends={plotted.map((item) => ({
        label: item.name,
        title: item.name,
        color: colorOf(item.name),
        reading: item.reading
      }))}
      plotHeight={220}
    />
  );
  return (
    <div data-docker-chart={chartKey} data-docker-plotted={plottedNames.join('|')} data-docker-side={side ? 'yes' : 'no'}>
      {side ? (
        <div className="grid grid-cols-1 items-stretch gap-4 min-[900px]:grid-cols-[minmax(0,3fr)_minmax(0,1fr)]">
          <div className="min-w-0">{chart}</div>
          <div
            className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)]"
            data-docker-side-readout=""
          >
            {liveSelected.size > 0 ? (
              <button
                type="button"
                className="border-0 border-b border-solid border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-left text-[12px] text-[var(--color-primary)]"
                onClick={() => setSelected(new Set())}
              >
                {clearLabel}
              </button>
            ) : null}
            <ul className="m-0 flex-1 list-none overflow-y-auto p-0">
              {series.map((item) => {
                const on = liveSelected.has(item.name);
                const color = colorOf(item.name);
                return (
                  <li key={item.name} className="border-b border-solid border-[var(--color-border)] last:border-b-0">
                    <button
                      type="button"
                      aria-pressed={on}
                      data-docker-candidate={item.name}
                      data-docker-readout-selected={on ? 'true' : 'false'}
                      className={`flex w-full min-w-0 cursor-pointer items-center justify-between gap-2 border-0 px-3 py-2 text-left text-[13px] ${on ? 'bg-[var(--color-fill-1)]' : 'bg-[var(--color-bg)]'}`}
                      onClick={() => {
                        setSelected((current) => {
                          const next = new Set(Array.from(current).filter((name) => names.includes(name)));
                          if (next.has(item.name)) next.delete(item.name);
                          else next.add(item.name);
                          return next;
                        });
                      }}
                    >
                      <span className="flex min-w-0 flex-1 items-center gap-2">
                        <span
                          aria-hidden
                          className="inline-flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-[3px] border text-[10px] leading-none"
                          style={{
                            borderColor: color,
                            background: on ? color : 'transparent',
                            color: 'var(--color-bg)'
                          }}
                        >
                          {on ? '✓' : ''}
                        </span>
                        <span
                          aria-hidden
                          className="inline-block h-2 w-2 shrink-0 rounded-full"
                          style={{ background: color }}
                        />
                        <span className="min-w-0 truncate text-[var(--color-text-1)]" title={item.name}>{item.name}</span>
                      </span>
                      <span className="shrink-0 text-right font-semibold tabular-nums" style={{ color }}>
                        {item.reading || DOCKER_BLANK}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      ) : chart}
    </div>
  );
}

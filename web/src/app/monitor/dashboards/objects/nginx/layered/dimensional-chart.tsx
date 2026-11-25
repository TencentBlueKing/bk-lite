'use client';

import { useState } from 'react';
import type { MetricUnit } from '../../../shared/types';
import ThinTimeSeries from '../../host/layered/thin-time-series';
import { chartRows, type NginxSeriesItem } from './model';
import { NginxHint } from './nginx-hint';
import type { NginxHintCopy } from './hints';
import { nonNegativeBounds } from './format';
import { filterPlotted } from './selection';

export function NginxDimensionalChart({
  title,
  hint,
  items,
  floor,
  formatReading,
  unit = 'none',
  stack = false,
  loading = false,
  emptyText = '暂无数据'
}: {
  title: string;
  hint?: NginxHintCopy;
  items: readonly NginxSeriesItem[];
  floor: number;
  formatReading: (value: number) => string;
  unit?: MetricUnit;
  stack?: boolean;
  loading?: boolean;
  emptyText?: string;
}) {
  const [selected, setSelected] = useState<ReadonlySet<string>>(() => new Set());
  const plotted = filterPlotted(items, selected);
  const data = chartRows(plotted);
  const legends = plotted.map((item) => ({
    label: item.label,
    color: item.color,
    title: item.label,
    reading: item.reading
  }));
  const toggle = (id: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  const chart = (
    <ThinTimeSeries
      title={title}
      hintNode={hint ? <NginxHint copy={hint} /> : undefined}
      data={data}
      legends={legends}
      unit={unit}
      loading={loading}
      emptyText={emptyText}
      reading={items.length === 1 ? items[0]?.reading : undefined}
      hideLegend={items.length > 1}
      pinAxisZero
      floorStrokeLiftPx={8}
      stackId={stack ? 'nginx-stack' : undefined}
      formatReading={formatReading}
      resolveValueBounds={(samples) => nonNegativeBounds(samples, floor)}
    />
  );
  if (items.length <= 1) return chart;
  const picker = items.length > 3 ? (
    <ul
      className="m-0 flex h-full list-none flex-col overflow-y-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-0"
      data-nginx-readout=""
    >
      {items.map((item) => {
        const on = selected.has(item.id);
        return (
          <li key={item.id} className="border-b border-solid border-[var(--color-border)] last:border-b-0">
            <button
              type="button"
              aria-pressed={on}
              data-nginx-readout-selected={on ? 'true' : 'false'}
              className={`flex w-full min-w-0 cursor-pointer items-center justify-between gap-2 border-0 px-2 py-2 text-left text-[13px] ${on ? 'bg-[var(--color-fill-1)]' : 'bg-[var(--color-bg)]'}`}
              onClick={() => toggle(item.id)}
            >
              <span className="flex min-w-0 flex-1 items-center gap-2">
                <span
                  aria-hidden
                  className="inline-flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-[3px] border text-[10px] leading-none"
                  style={{
                    borderColor: item.color,
                    background: on ? item.color : 'transparent',
                    color: 'var(--color-bg)'
                  }}
                >
                  {on ? '✓' : ''}
                </span>
                <span className="min-w-0 truncate text-[var(--color-text-1)]" title={item.label}>{item.label}</span>
              </span>
              <span className="shrink-0 text-right font-semibold tabular-nums" style={{ color: item.color }}>
                {item.reading}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  ) : (
    <div className="flex flex-wrap gap-2 px-3 pb-3" data-nginx-legend="">
      {items.map((item) => {
        const on = selected.has(item.id);
        return (
          <button
            key={item.id}
            type="button"
            aria-pressed={on}
            data-nginx-legend-selected={on ? 'true' : 'false'}
            className={`inline-flex max-w-full items-center gap-1.5 rounded-full border px-2 py-1 text-[12px] ${on ? 'border-transparent' : 'border-[var(--color-border)] bg-[var(--color-bg)]'}`}
            style={on ? { background: 'var(--color-fill-1)' } : undefined}
            onClick={() => toggle(item.id)}
          >
            <span className="inline-block h-2 w-2 shrink-0 rounded-full" style={{ background: item.color }} />
            <span className="truncate text-[var(--color-text-1)]">{item.label}</span>
            <span className="font-semibold tabular-nums" style={{ color: item.color }}>{item.reading}</span>
          </button>
        );
      })}
    </div>
  );
  if (items.length > 3) {
    return (
      <div
        className="grid grid-cols-1 items-stretch gap-3 min-[900px]:grid-cols-[minmax(0,3fr)_minmax(0,1fr)]"
        data-nginx-side-readout=""
      >
        <div className="min-w-0">{chart}</div>
        <div className="min-h-[180px]">{picker}</div>
      </div>
    );
  }
  return (
    <div data-nginx-legend-chart="">
      {chart}
      {picker}
    </div>
  );
}

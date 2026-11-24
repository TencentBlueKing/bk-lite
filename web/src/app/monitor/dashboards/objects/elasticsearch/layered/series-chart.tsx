'use client';

import { useMemo, useState } from 'react';
import type { ChartData } from '@/app/monitor/types';
import { ProInfoHint, ThinTimeSeries } from '../../host/layered/pro-chrome';
import { ES_PALETTE } from '../config';
import { dimensionChrome, selectedLineIds } from './model';
import { formatEsValue, type EsChartModel, type EsLineModel } from './assemble';

const LINE_COLORS = [
  ES_PALETTE.blue,
  ES_PALETTE.orange,
  ES_PALETTE.emerald,
  ES_PALETTE.cyan,
  ES_PALETTE.indigo,
  ES_PALETTE.amber,
  ES_PALETTE.rose
] as const;

const colorAt = (index: number) => LINE_COLORS[index % LINE_COLORS.length];

const toChartData = (lines: readonly EsLineModel[]): ChartData[] => {
  const byTime = new Map<number, ChartData>();
  lines.forEach((line, index) => {
    const key = `value${index + 1}`;
    line.points.forEach((point) => {
      const row = byTime.get(point.time) ?? { time: point.time };
      row[key] = point.value;
      byTime.set(point.time, row);
    });
  });
  return [...byTime.values()].sort((left, right) => Number(left.time) - Number(right.time));
};

function Hint({ title, body }: { title: string; body: string }) {
  return (
    <ProInfoHint
      kind="elasticsearch"
      label={`${title} ${body}`}
      content={(
        <div className="max-w-[380px] whitespace-pre-line text-[13px] font-normal leading-[1.55] text-[var(--color-text-2)]">
          {body}
        </div>
      )}
    />
  );
}

function LegendButton({
  line,
  color,
  pressed,
  onToggle
}: {
  line: EsLineModel;
  color: string;
  pressed: boolean;
  onToggle: (id: string) => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      data-es-series={line.id}
      data-es-selected={pressed ? 'true' : 'false'}
      className={`inline-flex min-w-0 items-center gap-1.5 border-0 bg-transparent px-0 text-left text-[12px] ${pressed ? '' : 'opacity-45'}`}
      onClick={() => onToggle(line.id)}
    >
      <span aria-hidden className="inline-block h-2 w-2 shrink-0 rounded-full" style={{ background: color }} />
      <span className="truncate text-[var(--color-text-1)]">{line.label}</span>
      <span className="shrink-0 font-semibold tabular-nums" style={{ color }}>{line.reading}</span>
    </button>
  );
}

export function EsSeriesChart({ chart }: { chart: EsChartModel }) {
  const [selected, setSelected] = useState<ReadonlySet<string>>(() => new Set());
  const chrome = dimensionChrome(chart.lines.length);
  const plottedIds = selectedLineIds(chart.lines.map((line) => line.id), selected);
  const plottedLines = chart.lines.filter((line) => plottedIds.includes(line.id) && line.fresh && line.points.length > 0);
  const data = useMemo(() => toChartData(plottedLines), [plottedLines]);
  const legends = plottedLines.map((line) => ({
    label: line.label,
    color: colorAt(chart.lines.findIndex((item) => item.id === line.id))
  }));
  const toggle = (id: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  const hint = <Hint title={chart.hintTitle} body={chart.hintBody} />;
  const plot = (
    <ThinTimeSeries
      bare
      title={chart.title}
      hintNode={hint}
      data={chart.state === 'value' ? data : []}
      legends={legends}
      unit={chart.format === 'percent' ? 'percent' : chart.format === 'counts' ? 'counts' : chart.format === 'bytes' ? 'bytes' : chart.format === 'byteps' ? 'byteps' : chart.format === 'cps' ? 'cps' : 'msps'}
      loading={chart.state === 'loading'}
      emptyText="暂无数据"
      hideLegend
      pinAxisZero={chart.pinZero}
      uniformZeroStrokeLiftPx={8}
      formatReading={(value) => formatEsValue(value, chart.format)}
    />
  );
  return (
    <section className="min-w-0 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-3" data-es-chart={chart.id} data-es-chart-state={chart.state}>
      {chrome === 'rail' ? (
        <div className="grid grid-cols-1 items-stretch gap-3 min-[900px]:grid-cols-4" data-es-dimension="rail">
          <div className="min-w-0 min-[900px]:col-span-3">{plot}</div>
          <ul className="m-0 flex max-h-[280px] list-none flex-col overflow-y-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] p-0 min-[900px]:max-h-none" data-es-rail="">
            {chart.lines.map((line, index) => {
              const pressed = selected.has(line.id);
              const color = colorAt(index);
              return (
                <li key={line.id} className="border-b border-solid border-[var(--color-border)] last:border-b-0">
                  <button
                    type="button"
                    aria-pressed={pressed}
                    data-es-series={line.id}
                    data-es-selected={pressed ? 'true' : 'false'}
                    className={`flex w-full min-w-0 cursor-pointer items-center justify-between gap-2 border-0 px-2 py-2 text-left text-[13px] ${pressed ? 'bg-[var(--color-fill-1)]' : 'bg-[var(--color-bg)]'}`}
                    onClick={() => toggle(line.id)}
                  >
                    <span className="flex min-w-0 flex-1 items-center gap-2">
                      <span
                        aria-hidden
                        className="inline-flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-[3px] border text-[10px] leading-none"
                        style={{ borderColor: color, background: pressed ? color : 'transparent', color: 'var(--color-bg)' }}
                      >
                        {pressed ? '✓' : ''}
                      </span>
                      <span aria-hidden className="inline-block h-2 w-2 shrink-0 rounded-full" style={{ background: color }} />
                      <span className="min-w-0 truncate text-[var(--color-text-1)]">{line.label}</span>
                    </span>
                    <span className="shrink-0 font-semibold tabular-nums" style={{ color }}>{line.reading}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ) : (
        <div data-es-dimension={chrome}>
          {plot}
          {chrome === 'legend' ? (
            <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1" data-es-legend="">
              {chart.lines.map((line, index) => (
                <LegendButton
                  key={line.id}
                  line={line}
                  color={colorAt(index)}
                  pressed={selected.size === 0 || selected.has(line.id)}
                  onToggle={toggle}
                />
              ))}
            </div>
          ) : null}
        </div>
      )}
    </section>
  );
}

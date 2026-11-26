'use client';

import { useState, type ReactNode } from 'react';
import { ExclamationCircleOutlined } from '@ant-design/icons';
import ProDashLoading from '../../host/layered/pro-dash-loading';
import { type NginxSeriesItem, type Point } from './model';
import { NginxHint } from './nginx-hint';
import type { NginxHintCopy } from './hints';
import { NginxPlot } from './nginx-plot';
import type { NginxQueryPhase } from './query-phase';

const CARD = 'flex min-w-0 flex-col rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)]';

export function NginxRetryBanner({
  visible,
  onRetry
}: {
  visible: boolean;
  onRetry: () => void;
}) {
  if (!visible) return null;
  return (
    <div
      className="flex items-center justify-between gap-3 rounded-lg px-3 py-2 text-[13px] text-[var(--color-text-1)]"
      style={{ background: 'color-mix(in srgb, var(--color-fail) 12%, transparent)' }}
      data-nginx-retry-banner=""
    >
      <span>部分数据加载失败</span>
      <button type="button" className="text-[var(--color-primary)]" onClick={onRetry}>全部重试</button>
    </div>
  );
}

function CardStatus({
  phase,
  emptyText,
  onRetry
}: {
  phase: NginxQueryPhase | 'empty';
  emptyText: string;
  onRetry?: () => void;
}) {
  if (phase === 'loading') {
    return (
      <div className="flex h-full items-center justify-center">
        <ProDashLoading />
      </div>
    );
  }
  if (phase === 'error') {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-[14px] text-[var(--color-text-3)]">
        <ExclamationCircleOutlined className="text-[20px]" />
        加载失败
        {onRetry ? (
          <button type="button" className="text-[var(--color-primary)]" onClick={onRetry}>重试</button>
        ) : null}
      </div>
    );
  }
  return (
    <div className="flex h-full items-center justify-center px-3 text-center text-[14px] text-[var(--color-text-3)]">
      {emptyText}
    </div>
  );
}

export function NginxSpark({ points, step = false }: { points: readonly Point[]; step?: boolean }) {
  if (points.length < 1) return <div className="h-6" />;
  const width = 160;
  const height = 24;
  const values = points.map((point) => point.value);
  const min = Math.min(0, ...values);
  const max = Math.max(...values, min + 1);
  const coords = points.map((point, index) => {
    const x = points.length === 1 ? width / 2 : (index / (points.length - 1)) * width;
    const y = height - 2 - ((point.value - min) / (max - min)) * (height - 4);
    return [x, y] as const;
  });
  let path = '';
  coords.forEach((coord, index) => {
    if (index === 0) {
      path += `M${coord[0]},${coord[1]}`;
      return;
    }
    const previous = coords[index - 1];
    path += step ? `H${coord[0]}V${coord[1]}` : `L${coord[0]},${coord[1]}`;
    if (!step && previous) return;
  });
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-6 w-full" preserveAspectRatio="none" aria-hidden="true">
      <path d={path} fill="none" stroke="var(--color-primary)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

export function NginxTile({
  anchor,
  label,
  hint,
  unit,
  figure,
  sub,
  tone,
  spark,
  sparkStep = false,
  progress,
  phase = 'ready',
  emptyText = '暂无数据',
  onRetry,
  onActivate,
  extra
}: {
  anchor?: string;
  label: string;
  hint?: NginxHintCopy | readonly NginxHintCopy[];
  unit?: string;
  figure: string;
  sub?: string;
  tone?: string;
  spark?: readonly Point[];
  sparkStep?: boolean;
  progress?: number | null;
  phase?: NginxQueryPhase;
  emptyText?: string;
  onRetry?: () => void;
  onActivate?: () => void;
  extra?: ReactNode;
}) {
  const quiet = phase !== 'ready' || figure === '暂无数据';
  const body = (
    <>
      <div className="flex items-center justify-between gap-2">
        <div className="inline-flex min-w-0 items-center gap-1 text-[14px] font-semibold text-[var(--color-text-1)]">
          <span className="truncate">{label}</span>
          {hint ? <NginxHint copy={hint} /> : null}
        </div>
        {unit ? <span className="shrink-0 text-[12px] text-[var(--color-text-3)]">{unit}</span> : null}
      </div>
      {phase !== 'ready' ? (
        <div className="min-h-0 flex-1">
          <CardStatus phase={phase} emptyText={emptyText} onRetry={onRetry} />
        </div>
      ) : quiet ? (
        <div className="flex flex-1 flex-col items-center justify-center text-center">
          <div className="text-[14px] text-[var(--color-text-3)]">{figure}</div>
          {sub ? <div className="mt-1 text-[12px] text-[var(--color-text-3)]">{sub}</div> : null}
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col justify-end">
          <div className="flex items-end justify-between gap-2">
            <div className="text-[28px] font-semibold leading-none tabular-nums text-[var(--color-text-1)]" style={tone ? { color: tone } : undefined}>
              {figure}
            </div>
            {extra}
          </div>
          {sub ? <div className="mt-1 text-[12px] text-[var(--color-text-3)]">{sub}</div> : null}
          {spark ? <NginxSpark points={spark} step={sparkStep} /> : null}
          {progress != null ? (
            <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-fill-2)]">
              <div
                className="h-full rounded-full bg-[var(--color-primary)]"
                style={{ width: `${Math.max(0, Math.min(100, progress))}%` }}
              />
            </div>
          ) : null}
        </div>
      )}
    </>
  );
  const className = `${CARD} h-[104px] px-3 py-2.5`;
  if (onActivate && phase === 'ready') {
    return (
      <button id={anchor} type="button" className={`${className} cursor-pointer text-left`} onClick={onActivate} data-nginx-tile={label}>
        {body}
      </button>
    );
  }
  return (
    <section id={anchor} className={className} data-nginx-tile={label}>
      {body}
    </section>
  );
}

export function NginxFocusTile({
  label,
  hint,
  unit,
  figure,
  sub,
  phase = 'ready',
  emptyText = '暂无数据',
  onRetry,
  onOpen
}: {
  label: string;
  hint?: NginxHintCopy | readonly NginxHintCopy[];
  unit?: string;
  figure: string;
  sub?: string;
  phase?: NginxQueryPhase;
  emptyText?: string;
  onRetry?: () => void;
  onOpen?: () => void;
}) {
  const inner = (
    <>
      <div className="flex w-full items-center justify-between gap-2">
        <div className="inline-flex min-w-0 items-center gap-1 text-[14px] font-semibold text-[var(--color-text-1)]">
          <span className="truncate">{label}</span>
          {hint ? <NginxHint copy={hint} /> : null}
        </div>
        {unit ? <span className="shrink-0 text-[12px] font-normal text-[var(--color-text-3)]">{unit}</span> : null}
      </div>
      {phase !== 'ready' ? (
        <div className="min-h-0 flex-1"><CardStatus phase={phase} emptyText={emptyText} onRetry={onRetry} /></div>
      ) : (
        <>
          <div className={`text-[22px] font-semibold leading-tight tabular-nums ${figure === '暂无数据' ? 'text-[14px] font-normal text-[var(--color-text-3)]' : 'text-[var(--color-text-1)]'}`}>{figure}</div>
          {sub ? <div className="text-[12px] text-[var(--color-text-3)]">{sub}</div> : null}
        </>
      )}
    </>
  );
  const className = `${CARD} h-[136px] items-start gap-1 px-3 py-3 text-left`;
  if (!onOpen || phase !== 'ready') {
    return <section className={className} data-nginx-focus={label}>{inner}</section>;
  }
  return (
    <button type="button" className={`${className} cursor-pointer`} onClick={onOpen} data-nginx-focus={label}>
      {inner}
    </button>
  );
}

function LegendRow({ items }: { items: readonly NginxSeriesItem[] }) {
  const [open, setOpen] = useState(false);
  if (items.length <= 1) return null;
  const visible = items.slice(0, 4);
  const rest = items.slice(4);
  return (
    <div className="flex items-center justify-end gap-2 px-3 text-[12px]" data-nginx-legend="">
      {visible.map((item) => (
        <span key={item.id} className="inline-flex min-w-0 items-center gap-1 text-[var(--color-text-1)]">
          <span className="inline-block h-2 w-2 shrink-0 rounded-full" style={{ background: item.color }} />
          <span className="max-w-[120px] truncate" title={item.label}>{item.label}</span>
        </span>
      ))}
      {rest.length ? (
        <span className="relative">
          <button type="button" className="text-[var(--color-text-2)]" onClick={() => setOpen((value) => !value)}>+{rest.length}</button>
          {open ? (
            <span className="absolute right-0 top-5 z-10 flex w-max max-w-[240px] flex-col gap-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-2 shadow-sm">
              {rest.map((item) => (
                <span key={item.id} className="inline-flex items-center gap-1">
                  <span className="inline-block h-2 w-2 rounded-full" style={{ background: item.color }} />
                  {item.label}
                </span>
              ))}
            </span>
          ) : null}
        </span>
      ) : null}
    </div>
  );
}

export function NginxChartCard({
  anchor,
  title,
  hint,
  unit,
  items,
  floor,
  formatReading,
  phase = 'ready',
  emptyText = '暂无数据',
  onRetry,
  kind = 'line',
  percent = false,
  height = 280
}: {
  anchor?: string;
  title: string;
  hint?: NginxHintCopy | readonly NginxHintCopy[];
  unit?: string;
  items: readonly NginxSeriesItem[];
  floor: number;
  formatReading: (value: number) => string;
  phase?: NginxQueryPhase;
  emptyText?: string;
  onRetry?: () => void;
  kind?: 'line' | 'step' | 'bar';
  percent?: boolean;
  height?: number;
}) {
  const hasPoints = items.some((item) => item.points.length > 0);
  const chartStatus: NginxQueryPhase | 'empty' | 'ready' = phase !== 'ready' ? phase : hasPoints ? 'ready' : 'empty';
  return (
    <section id={anchor} className={CARD} style={{ height }} data-nginx-chart={title}>
      <div className="flex items-center justify-between gap-2 px-3 pt-3">
        <div className="inline-flex min-w-0 items-center gap-1 text-[14px] font-semibold text-[var(--color-text-1)]">
          <span className="truncate">{title}</span>
          {hint ? <NginxHint copy={hint} /> : null}
        </div>
        {unit ? <span className="shrink-0 text-[12px] text-[var(--color-text-3)]">{unit}</span> : null}
      </div>
      <LegendRow items={items} />
      <div className="min-h-0 flex-1">
        {chartStatus === 'ready' ? (
          <NginxPlot
            items={items}
            kind={kind}
            floor={floor}
            percent={percent}
            formatReading={formatReading}
            height={height - 64}
          />
        ) : (
          <CardStatus phase={chartStatus} emptyText={emptyText} onRetry={onRetry} />
        )}
      </div>
    </section>
  );
}

export function NginxRankCard({
  anchor,
  title,
  hint,
  rows,
  selected,
  onSelect,
  phase = 'ready',
  emptyText = '暂无数据',
  onRetry,
  formatValue
}: {
  anchor?: string;
  title: string;
  hint?: NginxHintCopy;
  rows: readonly { id: string; label: string; value: number | null }[];
  selected: string | null;
  onSelect: (id: string) => void;
  phase?: NginxQueryPhase;
  emptyText?: string;
  onRetry?: () => void;
  formatValue: (value: number) => string;
}) {
  const peak = rows.reduce((max, row) => Math.max(max, row.value ?? 0), 0);
  const cap = rows.length <= 1 ? 0.6 : 1;
  return (
    <section id={anchor} className={`${CARD} h-[280px]`} data-nginx-rank={title}>
      <div className="flex items-center gap-1 px-3 pt-3 text-[14px] font-semibold text-[var(--color-text-1)]">
        {title}
        {hint ? <NginxHint copy={hint} /> : null}
      </div>
      {phase !== 'ready' || !rows.length ? (
        <CardStatus phase={phase !== 'ready' ? phase : 'empty'} emptyText={emptyText} onRetry={onRetry} />
      ) : (
        <ul className="m-0 flex min-h-0 flex-1 list-none flex-col gap-2 overflow-y-auto px-3 py-3">
          {rows.map((row) => {
            const width = peak > 0 && row.value != null ? Math.max(4, (row.value / peak) * 100 * cap) : 0;
            const on = selected === row.id;
            return (
              <li key={row.id}>
                <button
                  type="button"
                  aria-pressed={on}
                  className={`flex w-full items-center gap-2 border-0 bg-transparent p-0 text-left text-[13px] ${on ? 'text-[var(--color-primary)]' : 'text-[var(--color-text-1)]'}`}
                  onClick={() => onSelect(row.id)}
                >
                  <span className="w-[38%] min-w-[120px] truncate" title={row.label}>{row.label}</span>
                  <span className="relative h-2 min-w-0 flex-1 rounded-full bg-[var(--color-fill-2)]">
                    <span className="absolute inset-y-0 left-0 rounded-full bg-[var(--color-primary)]" style={{ width: `${width}%` }} />
                  </span>
                  <span className="w-16 shrink-0 text-right tabular-nums">{row.value == null ? '--' : formatValue(row.value)}</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

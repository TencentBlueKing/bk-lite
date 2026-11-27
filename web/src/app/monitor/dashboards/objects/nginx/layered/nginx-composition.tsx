'use client';

import classic from '../../host/index.module.scss';
import { formatCount, formatDecimal } from './format';
import type { NginxHintCopy } from './hints';
import { NginxCardTitle } from './nginx-card';
import type { NginxQueryPhase } from './query-phase';

export interface NginxPiePart {
  id: string;
  label: string;
  color: string;
  value: number | null;
}

const arc = (start: number, end: number) => {
  const radius = 42;
  const cx = 50;
  const cy = 50;
  const large = end - start > Math.PI ? 1 : 0;
  const x1 = cx + radius * Math.cos(start);
  const y1 = cy + radius * Math.sin(start);
  const x2 = cx + radius * Math.cos(end);
  const y2 = cy + radius * Math.sin(end);
  return `M${cx},${cy} L${x1},${y1} A${radius},${radius} 0 ${large} 1 ${x2},${y2} Z`;
};

export function NginxCompositionCard({
  anchor,
  title,
  hint,
  parts,
  noun,
  headline,
  idleText,
  phase,
  emptyText,
  emptyDetail,
  onRetry
}: {
  anchor?: string;
  title: string;
  hint?: NginxHintCopy | readonly NginxHintCopy[];
  parts: readonly NginxPiePart[];
  noun: string;
  headline?: string;
  idleText?: string;
  phase: NginxQueryPhase;
  emptyText: string;
  emptyDetail?: string;
  onRetry?: () => void;
}) {
  const known = parts.every((part) => part.value != null);
  const values = parts.map((part) => Math.max(part.value ?? 0, 0));
  const sum = values.reduce((total, value) => total + value, 0);
  const idle = Boolean(idleText) && known && sum === 0;
  const quiet = phase !== 'ready' || !known;
  let angle = -Math.PI / 2;
  const slices = parts.map((part, index) => {
    const sweep = sum === 0 ? 0 : (values[index] / sum) * Math.PI * 2;
    const start = angle;
    angle += sweep;
    return { part, start, end: angle, value: values[index] };
  });
  return (
    <section
      id={anchor}
      className={`${classic.panel} flex !h-[280px] h-full w-full min-w-0 flex-col`}
      data-nginx-pie={title}
      data-nginx-chart-kind="pie"
      data-nginx-pie-layout="stack"
    >
      <NginxCardTitle label={title} hint={hint} className="text-[14px] font-semibold text-[var(--color-text-1)]" />
      {quiet ? (
        <div className="flex min-h-0 flex-1 flex-col items-center justify-center text-center text-[var(--color-text-3)]">
          {phase === 'error' ? (
            <div className="flex flex-col items-center gap-2 text-[14px]">
              加载失败
              {onRetry ? <button type="button" className="text-[var(--color-primary)]" onClick={onRetry}>重试</button> : null}
            </div>
          ) : phase === 'loading' ? <div className="text-[14px]">加载中</div> : (
            <>
              <div className="text-[14px]" data-nginx-empty-title="">{emptyText}</div>
              {emptyDetail ? <div className="mt-1 text-[12px]" data-nginx-empty-detail="">{emptyDetail}</div> : null}
            </>
          )}
        </div>
      ) : (
        <div className="mt-2 flex min-h-0 flex-1 flex-col items-center gap-2 overflow-hidden">
          <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-1">
            {headline ? <div className="text-[13px] text-[var(--color-text-2)]">{headline}</div> : null}
            {idle ? (
              <div className="text-center text-[14px] text-[var(--color-text-3)]">{idleText}</div>
            ) : (
              <svg viewBox="0 0 100 100" className="h-[112px] w-[112px]" data-nginx-pie-shape="" aria-hidden="true">
                {slices.map((slice) => {
                  const sweep = slice.end - slice.start;
                  if (!(sweep > 0)) return null;
                  if (sweep >= Math.PI * 2 - 1e-4) {
                    return <circle key={slice.part.id} cx="50" cy="50" r="42" fill={slice.part.color} />;
                  }
                  return <path key={slice.part.id} d={arc(slice.start, slice.end)} fill={slice.part.color} />;
                })}
              </svg>
            )}
          </div>
          <ul className="m-0 flex w-full list-none flex-col gap-1 overflow-y-auto text-[12px] text-[var(--color-text-1)]">
            {slices.map((slice) => {
              const share = sum === 0 ? 0 : (slice.value / sum) * 100;
              return (
                <li key={slice.part.id} className="flex items-center justify-between gap-2">
                  <span className="inline-flex min-w-0 items-center gap-2">
                    <span className="inline-block h-2 w-2 shrink-0 rounded-full" style={{ background: slice.part.color }} />
                    <span className="truncate">{slice.part.label}</span>
                  </span>
                  <span className="shrink-0 tabular-nums">{formatCount(slice.value, noun)} · {formatDecimal(share)}%</span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </section>
  );
}

'use client';

import { useMemo, useState, type ReactNode } from 'react';
import { Popover } from 'antd';
import type { ChartData } from '@/app/monitor/types';
import { ProInfoHint } from '../../host/layered/alert-event-hint';
import ThinTimeSeries from '../../host/layered/thin-time-series';
import { ES_LINE_COLORS } from './palette';
import {
  readingParts,
  type EsFocus,
  type EsKpi,
  type EsRank,
  type EsRankRow,
  type EsSeries,
  type EsStat,
  type EsTone,
  type EsTrend
} from './assemble';

const TONE_COLOR: Record<EsTone, string> = {
  success: 'var(--color-success)',
  warning: 'var(--color-warning)',
  fail: 'var(--color-fail)'
};

const DOT_COLOR = {
  green: 'var(--color-success)',
  yellow: 'var(--color-warning)',
  red: 'var(--color-fail)'
} as const;

export function EsHintIcon({ title, body, kind }: { title: string; body: string; kind: string }) {
  return (
    <ProInfoHint
      kind={kind}
      label={`${title} ${body}`}
      content={(
        <div className="max-w-[380px] text-[13px] font-normal leading-[1.55] text-[var(--color-text-2)]">
          <div className="font-semibold text-[var(--color-text-1)]">{title}</div>
          <div className="mt-1 whitespace-pre-line">{body}</div>
        </div>
      )}
    />
  );
}

function CardFrame({
  id,
  title,
  unit,
  hintTitle,
  hintBody,
  status,
  emptyText,
  onRetry,
  height,
  className,
  onClick,
  children
}: {
  id: string;
  title: string;
  unit?: string;
  hintTitle: string;
  hintBody: string;
  status: EsKpi['status'];
  emptyText?: string;
  onRetry?: () => void;
  height: number;
  className?: string;
  onClick?: () => void;
  children?: ReactNode;
}) {
  const busy = status === 'loading';
  const failed = status === 'error';
  const empty = status === 'empty';
  const Tag = onClick ? 'button' : 'section';
  return (
    <Tag
      type={onClick ? 'button' : undefined}
      onClick={onClick}
      className={`flex w-full min-w-0 flex-col overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-left ${className || ''}`}
      style={{ height }}
      data-es-card={id}
      data-es-card-state={status}
    >
      <div className="flex h-5 min-w-0 items-center gap-1">
        <span className="truncate text-[14px] font-semibold leading-5 text-[var(--color-text-1)]">{title}</span>
        <EsHintIcon title={hintTitle} body={hintBody} kind={`es-${id}`} />
        {unit ? <span className="ml-auto shrink-0 text-[12px] text-[var(--color-text-3)]">{unit}</span> : null}
      </div>
      {busy ? (
        <div className="flex flex-1 items-center justify-center text-[13px] text-[var(--color-text-3)]">加载中</div>
      ) : null}
      {failed ? (
        <div className="flex flex-1 items-center justify-center gap-2 text-[13px] text-[var(--color-text-3)]">
          <span>加载失败</span>
          {onRetry ? (
            <button type="button" className="text-[var(--color-primary)]" onClick={onRetry}>重试</button>
          ) : null}
        </div>
      ) : null}
      {empty ? (
        <div className="flex flex-1 items-center justify-center px-2 text-center text-[13px] text-[var(--color-text-3)]">
          {emptyText || '暂无数据'}
        </div>
      ) : null}
      {status === 'value' ? children : null}
    </Tag>
  );
}

export function KpiCard({ card, onOpenAlerts, onRetry }: { card: EsKpi; onOpenAlerts: () => void; onRetry: () => void }) {
  return (
    <CardFrame
      id={card.id}
      title={card.title}
      unit={card.unit}
      hintTitle={card.hint.title}
      hintBody={card.hint.body}
      status={card.status}
      emptyText={card.emptyText}
      onRetry={onRetry}
      height={104}
      onClick={card.opensAlerts && card.status === 'value' ? onOpenAlerts : undefined}
    >
      <div
        className="mt-1 truncate text-[24px] font-semibold leading-8 tabular-nums text-[var(--color-text-1)]"
        style={card.tone ? { color: TONE_COLOR[card.tone] } : undefined}
      >
        {card.dot ? (
          <span
            aria-hidden
            className="mr-2 inline-block h-2.5 w-2.5 rounded-full align-middle"
            style={{ background: DOT_COLOR[card.dot] }}
          />
        ) : null}
        {card.value}
      </div>
      {card.note ? <div className="truncate text-[12px] leading-4 text-[var(--color-text-3)]">{card.note}</div> : null}
    </CardFrame>
  );
}

export function FocusCard({ card, onOpen, onRetry }: { card: EsFocus; onOpen: (target: EsFocus['target']) => void; onRetry: () => void }) {
  return (
    <CardFrame
      id={card.id}
      title={card.title}
      hintTitle={card.hint.title}
      hintBody={card.hint.body}
      status={card.status}
      emptyText={card.emptyText}
      onRetry={onRetry}
      height={136}
      className="group relative"
      onClick={card.status === 'value' ? () => onOpen(card.target) : undefined}
    >
      <div
        className="mt-2 truncate text-[20px] font-semibold leading-7 text-[var(--color-text-1)]"
        style={card.tone ? { color: TONE_COLOR[card.tone] } : undefined}
      >
        {card.primary}
      </div>
      <div className="mt-1 line-clamp-2 text-[12px] leading-4 text-[var(--color-text-3)]">{card.secondary}</div>
      {card.status === 'value' ? (
        <span className="pointer-events-none absolute right-2 top-2 text-[12px] text-[var(--color-text-3)] opacity-0 group-hover:opacity-100">→</span>
      ) : null}
    </CardFrame>
  );
}

export function StatCard({ card, onRetry }: { card: EsStat; onRetry: () => void }) {
  return (
    <CardFrame
      id={card.id}
      title={card.title}
      hintTitle={card.hint.title}
      hintBody={card.hint.body}
      status={card.status}
      emptyText={card.emptyText}
      onRetry={onRetry}
      height={136}
    >
      <div className={`mt-2 grid flex-1 gap-2 ${card.figures.length > 2 ? 'grid-cols-3' : 'grid-cols-2'}`}>
        {card.figures.map((figure) => (
          <div key={figure.label} className="min-w-0">
            <div className="truncate text-[12px] text-[var(--color-text-3)]">{figure.label}</div>
            <div
              className="truncate text-[22px] font-semibold leading-7 tabular-nums text-[var(--color-text-1)]"
              style={figure.tone ? { color: TONE_COLOR[figure.tone] } : undefined}
            >
              {figure.value}
            </div>
          </div>
        ))}
      </div>
      {card.note ? <div className="truncate text-[12px] leading-4 text-[var(--color-text-3)]">{card.note}</div> : null}
    </CardFrame>
  );
}

function barWidth(row: EsRankRow, card: EsRank): string {
  if (row.stale || row.value == null || row.value <= 0 || card.full <= 0) return '0%';
  const ratio = Math.min(1, row.value / card.full);
  const width = card.single ? ratio * 0.6 : ratio;
  return `${Math.max(0, width * 100)}%`;
}

export function RankCard({ card, onRetry }: { card: EsRank; onRetry: () => void }) {
  return (
    <CardFrame
      id={card.id}
      title={card.title}
      unit={card.unit}
      hintTitle={card.hint.title}
      hintBody={card.hint.body}
      status={card.status}
      emptyText={card.emptyText}
      onRetry={onRetry}
      height={280}
    >
      <ul className="mt-2 mb-0 min-h-0 flex-1 list-none overflow-y-auto p-0">
        {card.rows.map((row) => (
          <li
            key={row.id}
            className="grid h-7 grid-cols-[minmax(0,34%)_minmax(0,1fr)_auto] items-center gap-2"
            title={row.stale
              ? `${row.fullName} 最近读数 ${row.sourceClock}`
              : `${row.fullName} ${row.text} ${card.unit} ${row.sourceClock}`}
          >
            <span className={`truncate text-[12px] ${row.stale ? 'text-[var(--color-text-4)]' : 'text-[var(--color-text-1)]'}`}>
              {row.label}
            </span>
            <span className="h-1.5 overflow-hidden rounded-full bg-[var(--color-fill-2)]">
              <span
                className="block h-full rounded-full bg-[var(--color-primary)]"
                style={{ width: barWidth(row, card), background: row.tone ? TONE_COLOR[row.tone] : undefined }}
              />
            </span>
            <span className={`w-12 text-right text-[12px] tabular-nums ${row.stale ? 'text-[var(--color-text-4)]' : 'text-[var(--color-text-1)]'}`}>
              {row.text}
            </span>
          </li>
        ))}
      </ul>
      {card.allZero ? <div className="text-[12px] text-[var(--color-text-3)]">各节点均为 0</div> : null}
    </CardFrame>
  );
}

const colorAt = (index: number) => ES_LINE_COLORS[index % ES_LINE_COLORS.length];

const toChartData = (series: readonly EsSeries[]): ChartData[] => {
  const byTime = new Map<number, ChartData>();
  series.forEach((line, index) => {
    const key = `value${index + 1}`;
    line.points.forEach((point) => {
      const row = byTime.get(point.time) ?? { time: point.time };
      row[key] = point.value;
      byTime.set(point.time, row);
    });
  });
  return [...byTime.values()].sort((left, right) => Number(left.time) - Number(right.time));
};

function TrendBody({
  card,
  series,
  onRetry
}: {
  card: EsTrend;
  series: readonly EsSeries[];
  onRetry: () => void;
}) {
  const data = useMemo(() => toChartData(series), [series]);
  const legends = series.map((line, index) => ({
    label: line.label,
    title: line.fullName,
    color: colorAt(card.series.findIndex((item) => item.id === line.id) >= 0
      ? card.series.findIndex((item) => item.id === line.id)
      : index)
  }));
  if (card.status !== 'value') {
    return (
      <div className="flex flex-1 items-center justify-center text-[13px] text-[var(--color-text-3)]">
        {card.status === 'loading' ? '加载中' : null}
        {card.status === 'error' ? (
          <>
            <span>加载失败</span>
            <button type="button" className="ml-2 text-[var(--color-primary)]" onClick={onRetry}>重试</button>
          </>
        ) : null}
        {card.status === 'empty' ? (card.emptyText || '暂无数据') : null}
      </div>
    );
  }
  return (
    <div className="relative min-h-0 flex-1">
      <ThinTimeSeries
        bare
        title=""
        data={data}
        legends={legends}
        unit={card.metricUnit}
        hideLegend
        pinAxisZero
        valueBounds={card.valueBounds}
        markZeroCount={Boolean(card.liftZero)}
        formatReading={(value) => {
          const format = card.metricUnit === 'percent'
            ? 'percent'
            : card.metricUnit === 'bytes'
              ? 'bytes'
              : card.metricUnit === 'byteps'
                ? 'byteps'
                : card.metricUnit === 'msps'
                  ? 'msps'
                  : card.metricUnit === 'cps'
                    ? 'cps'
                    : 'counts';
          const parts = readingParts(value, format);
          return parts.unit ? `${parts.text} ${parts.unit}` : parts.text;
        }}
        plotHeight={220}
      />
      {card.zeroOverlay ? (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-[13px] text-[var(--color-text-3)]">
          {card.zeroOverlay}
        </div>
      ) : null}
    </div>
  );
}

function SeriesLegend({
  card,
  visibleIds,
  onToggle
}: {
  card: EsTrend;
  visibleIds: ReadonlySet<string>;
  onToggle: (id: string, checked: boolean) => void;
}) {
  const ranked = [...card.series].sort((left, right) => right.average - left.average);
  const pinned = ranked.slice(0, 5);
  const extra = ranked.slice(5);
  const shown = card.series.filter((line) => visibleIds.has(line.id));
  return (
    <div className="flex min-w-0 items-center justify-end gap-2 text-[12px]">
      {shown.map((line) => {
        const color = colorAt(card.series.findIndex((item) => item.id === line.id));
        return (
          <span key={line.id} className="inline-flex min-w-0 items-center gap-1" title={line.fullName}>
            <span aria-hidden className="inline-block h-2 w-2 shrink-0 rounded-full" style={{ background: color }} />
            <span className="max-w-[120px] truncate text-[var(--color-text-2)]">{line.label}</span>
          </span>
        );
      })}
      {extra.length ? (
        <Popover
          trigger="hover"
          content={(
            <div className="flex max-h-60 flex-col gap-1">
              {extra.map((line) => (
                <label key={line.id} className="flex items-center gap-2 text-[12px]" title={line.fullName}>
                  <input
                    type="checkbox"
                    checked={visibleIds.has(line.id)}
                    onChange={(event) => onToggle(line.id, event.target.checked)}
                  />
                  <span>{line.label}</span>
                </label>
              ))}
            </div>
          )}
        >
          <button type="button" className="shrink-0 text-[var(--color-text-3)]">+{extra.length}</button>
        </Popover>
      ) : null}
      <span className="sr-only">{pinned.length}</span>
    </div>
  );
}

export function TrendCard({ card, onRetry }: { card: EsTrend; onRetry: () => void }) {
  const ranked = [...card.series].sort((left, right) => right.average - left.average);
  const pinned = new Set(ranked.slice(0, 5).map((line) => line.id));
  const [picked, setPicked] = useState<ReadonlySet<string>>(() => new Set());
  const visibleIds = new Set<string>([...pinned, ...picked]);
  const visible = card.series.filter((line) => visibleIds.has(line.id));
  return (
    <section
      className="flex h-[280px] min-w-0 flex-col overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2"
      data-es-card={card.id}
      data-es-card-state={card.status}
    >
      <div className="flex h-5 min-w-0 items-center gap-2">
        <span className="truncate text-[14px] font-semibold text-[var(--color-text-1)]">{card.title}</span>
        <EsHintIcon title={card.hint.title} body={card.hint.body} kind={`es-${card.id}`} />
        {card.unit ? <span className="shrink-0 text-[12px] text-[var(--color-text-3)]">{card.unit}</span> : null}
        <div className="ml-auto min-w-0">
          {card.status === 'value' && card.series.length > 1 ? (
            <SeriesLegend
              card={card}
              visibleIds={visibleIds}
              onToggle={(id, checked) => {
                setPicked((current) => {
                  const next = new Set(current);
                  if (checked) next.add(id);
                  else next.delete(id);
                  return next;
                });
              }}
            />
          ) : null}
        </div>
      </div>
      <div className="min-h-0 flex-1">
        <TrendBody card={{ ...card, series: visible }} series={visible} onRetry={onRetry} />
      </div>
    </section>
  );
}

export function HeapCard({ card, onRetry }: { card: EsTrend; onRetry: () => void }) {
  const [hidden, setHidden] = useState<ReadonlySet<string>>(() => new Set());
  const [query, setQuery] = useState('');
  const readings = card.readings ?? [];
  const visibleSeries = card.series.filter((line) => !hidden.has(line.fullName) && !hidden.has(line.id));
  const ranked = [...visibleSeries].sort((left, right) => right.average - left.average).slice(0, 5);
  const filtered = readings.filter((row) => {
    const text = query.trim().toLowerCase();
    if (!text) return true;
    return row.fullName.toLowerCase().includes(text) || row.label.toLowerCase().includes(text);
  });
  return (
    <section
      className="flex h-[280px] min-w-0 flex-col overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 @[1024px]:h-[280px]"
      data-es-card={card.id}
      data-es-card-state={card.status}
    >
      <div className="flex h-5 min-w-0 items-center gap-1">
        <span className="truncate text-[14px] font-semibold text-[var(--color-text-1)]">{card.title}</span>
        <EsHintIcon title={card.hint.title} body={card.hint.body} kind={`es-${card.id}`} />
        <span className="text-[12px] text-[var(--color-text-3)]">%</span>
      </div>
      <div className="mt-2 grid min-h-0 flex-1 grid-cols-1 gap-3 @[1024px]:grid-cols-12">
        <div className="min-h-0 min-w-0 @[1024px]:col-span-8">
          <TrendBody card={card} series={ranked.length ? ranked : visibleSeries} onRetry={onRetry} />
        </div>
        <div className="flex min-h-0 min-w-0 flex-col @[1024px]:col-span-4">
          {readings.length > 8 ? (
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索节点"
              className="mb-1 h-7 rounded border border-[var(--color-border)] bg-[var(--color-bg)] px-2 text-[12px] text-[var(--color-text-1)]"
            />
          ) : null}
          <ul className="mb-0 min-h-0 flex-1 list-none overflow-y-auto p-0">
            {filtered.map((row) => (
              <li key={row.id}>
                <button
                  type="button"
                  className="flex h-7 w-full items-center gap-2 border-0 bg-transparent px-1 text-left text-[12px]"
                  title={row.stale ? `${row.fullName} 最近读数 ${row.sourceClock}` : `${row.fullName} ${row.text}%`}
                  onClick={() => {
                    setHidden((current) => {
                      const next = new Set(current);
                      if (next.has(row.fullName)) next.delete(row.fullName);
                      else next.add(row.fullName);
                      return next;
                    });
                  }}
                >
                  <span
                    aria-hidden
                    className="inline-block h-2 w-2 shrink-0 rounded-full"
                    style={{ background: row.tone ? TONE_COLOR[row.tone] : 'var(--color-text-4)' }}
                  />
                  <span className={`min-w-0 flex-1 truncate ${row.stale || hidden.has(row.fullName) ? 'text-[var(--color-text-4)]' : 'text-[var(--color-text-1)]'}`}>
                    {row.label}
                  </span>
                  <span className="tabular-nums text-[var(--color-text-1)]">{row.stale ? '—' : row.text}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

export function spanClass(kind: 'quarter' | 'third' | 'half' | 'full', width: number): string {
  if (width > 0 && width < 1024) return 'col-span-12';
  if (width > 0 && width < 1280) {
    if (kind === 'quarter') return 'col-span-6';
    return 'col-span-12';
  }
  if (kind === 'quarter') return 'col-span-3';
  if (kind === 'third') return 'col-span-4';
  if (kind === 'half') return 'col-span-6';
  return 'col-span-12';
}

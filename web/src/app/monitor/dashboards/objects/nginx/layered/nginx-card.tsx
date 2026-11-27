'use client';

import { useState, type ReactNode } from 'react';
import { ExclamationCircleOutlined } from '@ant-design/icons';
import type { MetricUnit } from '../../../shared/types';
import { formatFocusUnitText } from '../../host/layered/focus-axis';
import { ProFocusCard, proChromeClass } from '../../host/layered/focus-card';
import FocusShortcutTitle from '../../host/layered/focus-shortcut-title';
import host from '../../host/layered/layered.module.scss';
import classic from '../../host/index.module.scss';
import ProDashLoading from '../../host/layered/pro-dash-loading';
import ThinTimeSeries from '../../host/layered/thin-time-series';
import { chartRows, type NginxSeriesItem } from './model';
import { NginxHint } from './nginx-hint';
import type { NginxHintCopy } from './hints';
import { NginxPlot } from './nginx-plot';
import type { NginxQueryPhase } from './query-phase';

const CARD = `${classic.panel} flex h-full w-full min-w-0 flex-col overflow-hidden`;

export const NGINX_SPAN = {
  quarter: 'flex w-full min-w-0 min-[1100px]:col-span-3',
  third: 'flex w-full min-w-0 min-[1100px]:col-span-4',
  half: 'flex w-full min-w-0 min-[1100px]:col-span-6',
  threeQuarter: 'flex w-full min-w-0 min-[1100px]:col-span-9'
} as const;

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
  emptyDetail,
  onRetry
}: {
  phase: NginxQueryPhase | 'empty';
  emptyText: string;
  emptyDetail?: string;
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
    <div className="flex h-full flex-col items-center justify-center px-3 text-center text-[var(--color-text-3)]">
      <div className="text-[14px]" data-nginx-empty-title="">{emptyText}</div>
      {emptyDetail ? <div className="mt-1 text-[12px]" data-nginx-empty-detail="">{emptyDetail}</div> : null}
    </div>
  );
}

export function NginxCardTitle({
  label,
  hint,
  unit,
  className
}: {
  label: string;
  hint?: NginxHintCopy | readonly NginxHintCopy[];
  unit?: string;
  className?: string;
}) {
  const unitText = formatFocusUnitText(unit);
  return (
    <div className={`inline-flex min-w-0 items-center gap-1 ${className ?? ''}`} data-nginx-title="">
      <span className="truncate">{label}</span>
      {hint ? <NginxHint copy={hint} /> : null}
      {unitText ? (
        <span className="shrink-0 font-normal text-[var(--color-text-3)]" data-nginx-unit="">{unitText}</span>
      ) : null}
    </div>
  );
}

const TILE_FRAME = `${host.kpiCard} ${host.kpiCard72} h-[72px] h-full w-full`;
const CARD_SHELL = 'flex h-full min-h-0 w-full min-w-0 flex-col';

function TileHeading({
  label,
  hint,
  unit
}: {
  label: string;
  hint?: NginxHintCopy | readonly NginxHintCopy[];
  unit?: string;
}) {
  return (
    <NginxCardTitle
      label={label}
      hint={hint}
      unit={unit}
      className="text-[12px] font-medium text-[var(--color-text-2)]"
    />
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
  phase?: NginxQueryPhase;
  emptyText?: string;
  onRetry?: () => void;
  onActivate?: () => void;
  extra?: ReactNode;
}) {
  const quiet = phase !== 'ready' || figure === '暂无数据';
  const figureNode = (
    <div
      className={`${host.kpiValue} !mt-0`}
      data-nginx-figure=""
      style={tone ? { color: tone } : undefined}
    >
      {figure}
    </div>
  );
  const body = !quiet ? (
    <div className="flex w-full flex-col">
      <TileHeading label={label} hint={hint} unit={unit} />
      <div className="mt-1 flex w-full items-baseline gap-2" data-nginx-figure-row="">
        {figureNode}
        {extra}
      </div>
    </div>
  ) : (
    <>
      <TileHeading label={label} hint={hint} unit={unit} />
      {phase !== 'ready' ? (
        <div className="min-h-0 w-full flex-1">
          <CardStatus phase={phase} emptyText={emptyText} onRetry={onRetry} />
        </div>
      ) : (
        <div className="mt-1 flex w-full flex-col">
          <div className="text-[14px] text-[var(--color-text-3)]" data-nginx-figure="">{figure}</div>
          {sub ? <div className="text-[12px] text-[var(--color-text-3)]" data-nginx-sub="">{sub}</div> : null}
        </div>
      )}
    </>
  );
  const content = <div className={CARD_SHELL}>{body}</div>;
  if (onActivate && phase === 'ready') {
    return (
      <button
        id={anchor}
        type="button"
        className={`${TILE_FRAME} cursor-pointer text-left`}
        onClick={onActivate}
        data-nginx-tile={label}
        data-nginx-kpi-height="72"
      >
        {content}
      </button>
    );
  }
  return (
    <section id={anchor} className={TILE_FRAME} data-nginx-tile={label} data-nginx-kpi-height="72">
      {content}
    </section>
  );
}

const lastFinite = (item: NginxSeriesItem) => {
  for (let index = item.points.length - 1; index >= 0; index -= 1) {
    const value = item.points[index]?.value;
    if (typeof value === 'number' && Number.isFinite(value)) return value;
  }
  return null;
};

export function NginxFocusTile({
  label,
  hint,
  unit,
  figure,
  sub,
  series = [],
  formatReading,
  tone,
  countAxis = false,
  phase = 'ready',
  emptyText = '暂无数据',
  emptyDetail,
  onRetry,
  onOpen
}: {
  label: string;
  hint?: NginxHintCopy | readonly NginxHintCopy[];
  unit?: string;
  figure: string;
  sub?: string;
  series?: readonly NginxSeriesItem[];
  formatReading?: (value: number) => string;
  tone?: string;
  countAxis?: boolean;
  phase?: NginxQueryPhase;
  emptyText?: string;
  emptyDetail?: string;
  onRetry?: () => void;
  onOpen?: () => void;
}) {
  const hasLine = series.some((item) => item.points.length > 0);
  const quietFigure = figure === '暂无数据' || figure === '--';
  const metricUnit: MetricUnit = countAxis ? 'counts' : 'cps';
  const title = (
    <div data-nginx-focus-title="">
      <FocusShortcutTitle
        label={label}
        unit={unit}
        hint={hint ? <NginxHint copy={hint} /> : undefined}
      />
    </div>
  );
  const headline = phase === 'ready' ? (
    <>
      {quietFigure ? (
        <div className="text-[14px] text-[var(--color-text-3)]" data-nginx-figure="">{figure}</div>
      ) : (
        <div
          className={proChromeClass.shortcutValue}
          data-nginx-figure=""
          data-nginx-figure-row=""
          style={tone ? { color: tone } : undefined}
        >
          {figure}
        </div>
      )}
      {sub ? <div className={proChromeClass.shortcutSub} data-nginx-sub="">{sub}</div> : null}
    </>
  ) : null;
  const plot = phase !== 'ready' ? (
    <div className={`${proChromeClass.focusChart} h-full min-h-0`} data-nginx-focus-plot="">
      <CardStatus phase={phase} emptyText={emptyText} onRetry={onRetry} />
    </div>
  ) : hasLine ? (
    <div className={`${proChromeClass.focusChart} h-full min-h-0`} data-nginx-focus-plot="" data-nginx-spark="">
      <ThinTimeSeries
        bare
        numericAxis
        padValueAxis
        axisNumbersOnly
        hideLegend
        className="flex h-full min-h-0 w-full flex-col"
        title=""
        unit={metricUnit}
        data={chartRows(series)}
        legends={series.map((item) => ({ label: item.label, color: item.color }))}
        formatReading={formatReading}
      />
    </div>
  ) : (
    <div className={`${proChromeClass.focusChart} h-full min-h-0`} data-nginx-focus-plot="">
      <CardStatus phase="empty" emptyText={emptyText} emptyDetail={emptyDetail} />
    </div>
  );
  return (
    <ProFocusCard
      className={`${host.focusCard168} h-[168px] h-full w-full`}
      data-nginx-focus={label}
      data-nginx-focus-layout="split"
      data-nginx-focus-height="168"
      data-nginx-width="1/3"
      onClick={phase === 'ready' && onOpen ? onOpen : undefined}
      role={phase === 'ready' && onOpen ? 'button' : undefined}
      tabIndex={phase === 'ready' && onOpen ? 0 : undefined}
    >
      <div className={proChromeClass.shortcutCopy} data-nginx-focus-copy="">
        {title}
        {headline}
      </div>
      {plot}
    </ProFocusCard>
  );
}

function LegendRow({
  items,
  showReadings
}: {
  items: readonly NginxSeriesItem[];
  showReadings: boolean;
}) {
  const [open, setOpen] = useState(false);
  if (!items.length) return null;
  if (!showReadings && items.length <= 1) return null;
  const visible = items.slice(0, 4);
  const rest = items.slice(4);
  return (
    <div className="flex items-center justify-end gap-2 text-[12px]" data-nginx-legend="">
      {visible.map((item) => (
        <span key={item.id} className="inline-flex min-w-0 items-center gap-1 text-[var(--color-text-1)]">
          <span className="inline-block h-2 w-2 shrink-0 rounded-full" style={{ background: item.color }} />
          <span className="max-w-[120px] truncate" title={item.label}>{item.label}</span>
          {showReadings && item.reading ? (
            <span className="shrink-0 tabular-nums text-[var(--color-text-2)]" data-nginx-legend-reading="">{item.reading}</span>
          ) : null}
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
  emptyDetail,
  onRetry,
  kind = 'line',
  percent = false,
  height = 280,
  countAxis = false
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
  emptyDetail?: string;
  onRetry?: () => void;
  kind?: 'line' | 'step' | 'bar';
  percent?: boolean;
  height?: number;
  countAxis?: boolean;
}) {
  const hasPoints = items.some((item) => item.points.length > 0);
  const chartStatus: NginxQueryPhase | 'empty' | 'ready' = phase !== 'ready' ? phase : hasPoints ? 'ready' : 'empty';
  const showReadings = kind !== 'bar' && items.length > 0 && items.length <= 3;
  const legendItems = items.map((item) => {
    if (!showReadings) return { ...item, reading: '' };
    const value = lastFinite(item);
    return { ...item, reading: value == null ? '' : formatReading(value) };
  });
  return (
    <section id={anchor} className={CARD} style={{ height }} data-nginx-chart={title} data-nginx-count-axis={countAxis ? '' : undefined}>
      <div className="flex items-center">
        <NginxCardTitle
          label={title}
          hint={hint}
          unit={unit}
          className="text-[14px] font-semibold text-[var(--color-text-1)]"
        />
      </div>
      <LegendRow items={legendItems} showReadings={showReadings} />
      <div className="min-h-0 flex-1">
        {chartStatus === 'ready' && kind === 'line' ? (
          <ThinTimeSeries
            bare
            hideLegend
            axisNumbersOnly
            pinAxisZero={!percent}
            floorStrokeLiftPx={8}
            valueBounds={percent ? { min: 0, max: 100 } : undefined}
            unit={countAxis ? 'counts' : percent ? 'percent' : 'none'}
            title=""
            data={chartRows(items)}
            legends={items.map((item) => ({ label: item.label, color: item.color }))}
            formatReading={formatReading}
            plotHeight={Math.max(120, height - 64)}
            className="flex h-full min-h-0 w-full flex-col"
          />
        ) : chartStatus === 'ready' ? (
          <NginxPlot
            items={items}
            kind={kind}
            floor={floor}
            percent={percent}
            countAxis={countAxis}
            formatReading={formatReading}
            height={height - 64}
          />
        ) : (
          <CardStatus phase={chartStatus} emptyText={emptyText} emptyDetail={phase === 'ready' ? emptyDetail : undefined} onRetry={onRetry} />
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
  emptyDetail,
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
  emptyDetail?: string;
  onRetry?: () => void;
  formatValue: (value: number) => string;
}) {
  const peak = rows.reduce((max, row) => Math.max(max, row.value ?? 0), 0);
  const cap = rows.length <= 1 ? 0.6 : 1;
  return (
    <section id={anchor} className={`${CARD} !h-[280px]`} data-nginx-rank={title}>
      <div className="flex items-center">
        <NginxCardTitle label={title} hint={hint} className="text-[14px] font-semibold text-[var(--color-text-1)]" />
      </div>
      {phase !== 'ready' || !rows.length ? (
        <CardStatus phase={phase !== 'ready' ? phase : 'empty'} emptyText={emptyText} emptyDetail={phase === 'ready' ? emptyDetail : undefined} onRetry={onRetry} />
      ) : (
        <ul className="m-0 flex min-h-0 flex-1 list-none flex-col gap-2 overflow-y-auto pt-3">
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

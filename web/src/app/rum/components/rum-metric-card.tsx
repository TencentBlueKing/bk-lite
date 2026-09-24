'use client';

import { useState, type ReactNode } from 'react';

import { toneTextClass, type CwvTone, type RumBadgeTone } from '@/app/rum/lib/cwv';

export interface RumMetricCell {
  value: ReactNode;
  label: ReactNode;
  tone?: RumBadgeTone;
  onClick?: () => void;
}

function metricValueClass(tone?: RumBadgeTone, isLongText = false): string {
  const sizeClass = isLongText ? 'text-sm sm:text-base font-medium' : 'text-xl sm:text-2xl font-bold';
  if (!tone || tone === 'neutral') return `text-[var(--color-text-1)] ${sizeClass}`;
  if (tone === 'info') return `text-[var(--color-primary)] ${sizeClass}`;
  return `${toneTextClass(tone as CwvTone)} ${sizeClass}`;
}

function getMetricWash(tone?: RumBadgeTone, hover = false): string {
  let hue = 'var(--color-primary)';
  if (tone === 'danger') hue = 'var(--color-fail)';
  else if (tone === 'warning') hue = 'var(--color-warning)';
  else if (tone === 'success') hue = 'var(--color-success)';

  const opacity = hover ? '3%' : '1.5%';
  const bg = hover ? 'var(--color-bg-hover)' : 'var(--color-bg)';
  return `linear-gradient(180deg, color-mix(in srgb, ${hue} ${opacity}, ${bg}) 0%, ${bg} 32%)`;
}

/**
 * RUM 指标卡：OpsPilot Look B 质感（超微弱水洗微光 + 柔和细边框 + 微阴影 + 结构化指标排版）
 * 1. 超浅水洗：浓度严格收敛至 1.5%，淡出范围收缩在顶部 32%，仅提供通透微光，绝不产生厚重色斑。
 * 2. 色彩呼应：有状态时微光与数值颜色（黄/红/绿）自然呼应，常规卡片统一透淡蓝微光，整排卡片均有底光，彻底杜绝“有的有底色、有的没有”。
 */
export function RumMetricCard({
  value,
  label,
  tone,
  onClick,
  className,
}: RumMetricCell & { className?: string }) {
  const [hover, setHover] = useState(false);
  const interactive = Boolean(onClick);
  const isLong = typeof value === 'string' && value.length > 8;

  const rootClass = [
    'min-w-0 rounded-lg border border-[var(--color-border-1)] p-3 sm:px-3.5 sm:py-3 text-left transition-[background,border-color,box-shadow] duration-150 shadow-[0_1px_3px_rgba(0,0,0,0.03)]',
    interactive
      ? 'group cursor-pointer hover:border-[var(--color-primary)] hover:shadow-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[color-mix(in_srgb,var(--color-primary)_45%,transparent)]'
      : 'cursor-default',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  const wash = getMetricWash(tone, hover && interactive);

  const body = (
    <div className="flex flex-col justify-between gap-1.5 h-full">
      <div className="flex items-center justify-between gap-1.5">
        <span
          className={[
            'text-xs font-medium text-[var(--color-text-3)] transition-colors truncate',
            interactive ? 'group-hover:text-[var(--color-primary)]' : '',
          ]
            .filter(Boolean)
            .join(' ')}
        >
          {label}
        </span>
      </div>
      <div className={`font-mono tracking-tight tabular-nums ${isLong ? 'whitespace-normal break-words leading-snug' : 'truncate'} ${metricValueClass(tone, isLong)}`}>
        {value}
      </div>
    </div>
  );

  if (interactive) {
    return (
      <button
        type="button"
        onClick={onClick}
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
        className={rootClass}
        style={{ background: wash }}
      >
        {body}
      </button>
    );
  }

  return (
    <div
      className={rootClass}
      style={{ background: wash }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      {body}
    </div>
  );
}

/**
 * 指标格：白底细边框 + gap，按数量均分铺满。
 */
export function RumMetricGrid({
  cells,
  className,
  cellClassName,
}: {
  cells: RumMetricCell[];
  className?: string;
  cellClassName?: string;
}) {
  const grid =
    cells.length <= 3
      ? 'grid-cols-3'
      : cells.length === 4
        ? 'grid-cols-2 sm:grid-cols-4'
        : 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-6';
  return (
    <div className={['grid min-w-0 gap-3', grid, className].filter(Boolean).join(' ')}>
      {cells.map((cell, index) => (
        <RumMetricCard
          key={typeof cell.label === 'string' ? cell.label : `metric-${index}`}
          {...cell}
          className={cellClassName}
        />
      ))}
    </div>
  );
}

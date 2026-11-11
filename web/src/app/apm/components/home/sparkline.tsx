'use client';

import { useId } from 'react';

type SparklineKind = 'line' | 'area';

interface SparklineProps {
  data: ReadonlyArray<number | null>;
  /** Logical viewBox width; SVG stretches to container width unless `fit="fixed"`. */
  width?: number;
  height?: number;
  color?: string;
  kind?: SparklineKind;
  fillOpacity?: number;
  className?: string;
  /**
   * `fill`（默认）：横向铺满容器，高度用 `height`。
   * `fixed`：按 `width`/`height` 像素旁挂，不拉伸占满。
   */
  fit?: 'fill' | 'fixed';
}

/**
 * SVG sparkline. Uses `currentColor` so CSS variables (and theme tokens)
 * resolve correctly — SVG presentation attributes often ignore `var(...)`.
 */
export default function Sparkline({
  data,
  width = 200,
  height = 28,
  color = 'var(--color-primary)',
  kind = 'line',
  fillOpacity = 0.18,
  className = '',
  fit = 'fill',
}: SparklineProps) {
  const reactId = useId().replace(/:/g, '');
  const samples = data.map((value) => (typeof value === 'number' && Number.isFinite(value) ? value : null));
  const finite = samples.filter((value): value is number => value !== null);
  if (finite.length === 0) return null;

  const pad = 1;
  const min = Math.min(...finite);
  const max = Math.max(...finite);
  const flat = max === min;
  const range = flat ? 1 : max - min;
  const xStep = (width - pad * 2) / Math.max(samples.length - 1, 1);
  // Flat series (e.g. all zeros) sits mid-band so KPI cards don't look like a bottom border.
  const midY = height * 0.55;

  const points = samples.map((value, index) => {
    if (value === null) return null;
    const x = pad + index * xStep;
    const y = flat ? midY : pad + (height - pad * 2) * (1 - (value - min) / range);
    return [x, y] as const;
  });
  const segments: Array<Array<readonly [number, number]>> = [];
  let current: Array<readonly [number, number]> = [];
  for (const point of points) {
    if (!point) {
      if (current.length) segments.push(current);
      current = [];
      continue;
    }
    current.push(point);
  }
  if (current.length) segments.push(current);
  const linePath = (segment: Array<readonly [number, number]>) =>
    segment.map(([x, y], index) => (index === 0 ? `M ${x} ${y}` : `L ${x} ${y}`)).join(' ');
  const areaPath = (segment: Array<readonly [number, number]>) => {
    const line = linePath(segment);
    return `${line} L ${segment[segment.length - 1][0]} ${height - pad} L ${segment[0][0]} ${height - pad} Z`;
  };
  const gradId = `spark-area-${reactId}`;
  const fixed = fit === 'fixed';

  return (
    <div
      className={`${fixed ? 'shrink-0' : 'w-full min-w-0'} ${className}`}
      style={{ color, width: fixed ? width : undefined }}
      aria-hidden="true"
    >
      <svg
        className="block w-full"
        style={{ height }}
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
      >
        {kind === 'area' ? (
          <>
            <defs>
              <linearGradient id={gradId} x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor="currentColor" stopOpacity={fillOpacity} />
                <stop offset="100%" stopColor="currentColor" stopOpacity={0} />
              </linearGradient>
            </defs>
            {segments.map((segment, index) =>
              segment.length < 2 ? (
                <circle key={index} cx={segment[0][0]} cy={segment[0][1]} r={1.5} fill="currentColor" />
              ) : (
                <path key={`area-${index}`} d={areaPath(segment)} fill={`url(#${gradId})`} />
              ),
            )}
            {segments.map((segment, index) =>
              segment.length < 2 ? null : (
                <path
                  key={`line-${index}`}
                  d={linePath(segment)}
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={1.5}
                  strokeLinejoin="round"
                  strokeLinecap="round"
                  vectorEffect="non-scaling-stroke"
                />
              ),
            )}
          </>
        ) : (
          segments.map((segment, index) =>
            segment.length < 2 ? (
              <circle key={index} cx={segment[0][0]} cy={segment[0][1]} r={1.5} fill="currentColor" />
            ) : (
              <path
                key={index}
                d={linePath(segment)}
                fill="none"
                stroke="currentColor"
                strokeWidth={1.5}
                strokeLinejoin="round"
                strokeLinecap="round"
                vectorEffect="non-scaling-stroke"
              />
            ),
          )
        )}
      </svg>
    </div>
  );
}

export function toSparklineData(values: (number | null)[]): number[] {
  return values.map((value) => value ?? 0);
}

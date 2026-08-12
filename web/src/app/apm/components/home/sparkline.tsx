'use client';

import { useId } from 'react';

type SparklineKind = 'line' | 'area';

interface SparklineProps {
  data: number[];
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
  if (data.length === 0) return null;

  const pad = 1;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const flat = max === min;
  const range = flat ? 1 : max - min;
  const xStep = (width - pad * 2) / Math.max(data.length - 1, 1);
  // Flat series (e.g. all zeros) sits mid-band so KPI cards don't look like a bottom border.
  const midY = height * 0.55;

  const points = data.map((v, i) => {
    const x = pad + i * xStep;
    const y = flat ? midY : pad + (height - pad * 2) * (1 - (v - min) / range);
    return [x, y] as const;
  });
  const linePath = points
    .map(([x, y], i) => (i === 0 ? `M ${x} ${y}` : `L ${x} ${y}`))
    .join(' ');
  const areaPath = `${linePath} L ${points[points.length - 1][0]} ${height - pad} L ${points[0][0]} ${height - pad} Z`;
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
            <path d={areaPath} fill={`url(#${gradId})`} />
            <path
              d={linePath}
              fill="none"
              stroke="currentColor"
              strokeWidth={1.5}
              strokeLinejoin="round"
              strokeLinecap="round"
              vectorEffect="non-scaling-stroke"
            />
          </>
        ) : (
          <path
            d={linePath}
            fill="none"
            stroke="currentColor"
            strokeWidth={1.5}
            strokeLinejoin="round"
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
          />
        )}
      </svg>
    </div>
  );
}

export function toSparklineData(values: (number | null)[]): number[] {
  return values.map((value) => value ?? 0);
}

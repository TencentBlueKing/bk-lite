'use client';

interface DonutSegment {
  label: string;
  count: number;
  color: string;
}

interface DonutChartProps {
  data: DonutSegment[];
  size?: number;
  innerRatio?: number;
}

export default function DonutChart({ data, size = 180, innerRatio = 0.62 }: DonutChartProps) {
  const total = data.reduce((acc, d) => acc + d.count, 0);
  if (total === 0) return null;
  const cx = size / 2;
  const cy = size / 2;
  const r = size / 2 - 2;
  const ir = r * innerRatio;
  const gap = 0.012;

  let cumAngle = -Math.PI / 2;
  const paths = data.map((d) => {
    const angle = (d.count / total) * Math.PI * 2;
    const start = cumAngle + gap / 2;
    const end = cumAngle + angle - gap / 2;
    cumAngle += angle;
    if (end - start <= 0) return null;

    const x1 = cx + r * Math.cos(start);
    const y1 = cy + r * Math.sin(start);
    const x2 = cx + r * Math.cos(end);
    const y2 = cy + r * Math.sin(end);
    const ix1 = cx + ir * Math.cos(end);
    const iy1 = cy + ir * Math.sin(end);
    const ix2 = cx + ir * Math.cos(start);
    const iy2 = cy + ir * Math.sin(start);
    const largeArc = end - start > Math.PI ? 1 : 0;
    return {
      d:
        `M ${x1} ${y1} ` +
        `A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2} ` +
        `L ${ix1} ${iy1} ` +
        `A ${ir} ${ir} 0 ${largeArc} 0 ${ix2} ${iy2} Z`,
      color: d.color,
    };
  });

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
      {paths.map(
        (p, i) =>
          p && (
            <path
              key={i}
              d={p.d}
              style={{ fill: p.color, stroke: 'var(--color-bg)' }}
              strokeWidth={1}
            />
          ),
      )}
    </svg>
  );
}

/** Semantic fills for health donut — applied via style so CSS vars resolve. */
export const HEALTH_DONUT_COLORS: Record<string, string> = {
  healthy: 'var(--color-success)',
  warning: 'var(--theme-color-status-warning)',
  critical: 'var(--color-fail)',
  unknown: 'var(--color-text-4)',
};

'use client';

import { useCallback, useMemo, useRef, useState, type MouseEvent } from 'react';

import Sparkline from '@/app/apm/components/home/sparkline';
import { parseAlertTrendValue, type RumAlertTrendPoint } from '@/app/rum/api';

export default function AlertMetricTrend({
  points,
  emptyLabel,
  hoverHint,
  formatPoint,
}: {
  points: RumAlertTrendPoint[];
  emptyLabel: string;
  hoverHint: string;
  formatPoint: (atMs: number, value: number | null) => string;
}) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const values = useMemo(() => points.map((point) => parseAlertTrendValue(point.value)), [points]);
  const hasSample = values.some((value) => value !== null);

  const onMove = useCallback(
    (event: MouseEvent<HTMLDivElement>) => {
      const el = trackRef.current;
      if (!el || points.length === 0) return;
      const rect = el.getBoundingClientRect();
      if (rect.width <= 0) return;
      const ratio = (event.clientX - rect.left) / rect.width;
      const idx = Math.round(ratio * (points.length - 1));
      setHoverIdx(Math.max(0, Math.min(points.length - 1, idx)));
    },
    [points.length],
  );

  if (points.length === 0 || !hasSample) {
    return <p className="text-[var(--color-text-3)]">{emptyLabel}</p>;
  }

  const active = hoverIdx != null ? points[hoverIdx] : null;
  const tipLeft = hoverIdx == null || points.length <= 1 ? 50 : (hoverIdx / (points.length - 1)) * 100;
  const activeAtMs = active && Number.isFinite(active.atMs) ? active.atMs : 0;
  const activeValue = active ? parseAlertTrendValue(active.value) : null
  return (
    <div ref={trackRef} className="relative h-24 cursor-crosshair pt-2" onMouseMove={onMove} onMouseLeave={() => setHoverIdx(null)}>
      <Sparkline data={values} height={88} kind="area" color="var(--color-primary)" />
      {active ? (
        <div
          className="pointer-events-none absolute top-0 z-10 -translate-x-1/2 whitespace-nowrap rounded-md bg-[var(--color-bg)] px-2 py-1 tabular-nums text-[var(--color-text-1)] shadow-sm ring-1 ring-[var(--color-border-2)]"
          style={{ left: `${tipLeft}%` }}
        >
          {formatPoint(activeAtMs, activeValue)}
        </div>
      ) : (
        <p className="pointer-events-none absolute left-0 top-0 text-[var(--color-text-4)]">{hoverHint}</p>
      )}
    </div>
  );
}

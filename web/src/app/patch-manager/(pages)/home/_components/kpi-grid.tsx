'use client';

import React, { useLayoutEffect, useRef, useState } from 'react';

import { resolveSharedKpiFontSize } from '../kpiPresentation';
import KpiCard, { type KpiCardProps } from './kpi-card';

interface KpiGridProps {
  items: Omit<KpiCardProps, 'maxFontSize'>[];
}

const DEFAULT_KPI_CARD_WIDTH = 156;

export default function KpiGrid({ items }: KpiGridProps) {
  const gridRef = useRef<HTMLDivElement>(null);
  const [maxFontSize, setMaxFontSize] = useState(() =>
    resolveSharedKpiFontSize(DEFAULT_KPI_CARD_WIDTH),
  );

  useLayoutEffect(() => {
    const grid = gridRef.current;
    if (!grid) return undefined;

    let frameId = 0;
    const updateFontSize = () => {
      const firstCard = grid.firstElementChild;
      if (!(firstCard instanceof HTMLElement)) return;

      const nextFontSize = resolveSharedKpiFontSize(
        firstCard.getBoundingClientRect().width,
      );
      setMaxFontSize((current) =>
        Math.abs(current - nextFontSize) < 0.1 ? current : nextFontSize,
      );
    };

    updateFontSize();
    if (typeof ResizeObserver === 'undefined') return undefined;

    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frameId);
      frameId = requestAnimationFrame(updateFontSize);
    });
    observer.observe(grid);

    return () => {
      cancelAnimationFrame(frameId);
      observer.disconnect();
    };
  }, []);

  return (
    <div
      ref={gridRef}
      className="mb-3.5 grid grid-cols-[repeat(auto-fit,minmax(160px,1fr))] gap-3"
    >
      {items.map((item) => (
        <KpiCard
          key={item.label}
          {...item}
          maxFontSize={maxFontSize}
        />
      ))}
    </div>
  );
}

'use client';

import { Tooltip } from 'antd';

import type { RumViewDist } from '@/app/rum/api';
import { useTranslation } from '@/utils/i18n';

const SEGMENTS: { key: keyof RumViewDist; label: string; cls: string }[] = [
  { key: 'good', label: 'good', cls: 'bg-[var(--color-success)]' },
  { key: 'needsImprove', label: 'ni', cls: 'bg-[var(--theme-color-status-warning)]' },
  { key: 'poor', label: 'poor', cls: 'bg-[var(--color-fail)]' },
  { key: 'missing', label: 'missing', cls: 'bg-[var(--color-text-4)]' },
];

export default function DistributionBar({ dist }: { dist: RumViewDist }) {
  const { t } = useTranslation();
  const total = dist.good + dist.needsImprove + dist.poor + dist.missing;
  if (total <= 0) return <span className="text-xs text-[var(--color-text-3)]">—</span>;
  const goodPct = Math.round((dist.good / total) * 100);

  const tooltip = (
    <div className="flex flex-col gap-1 py-0.5 text-xs">
      <div className="font-medium">{t('rum.views.dist.label', 'CWV 分布')}</div>
      {SEGMENTS.map((seg) => {
        const n = dist[seg.key] || 0;
        if (n <= 0) return null;
        const pct = Math.round((n / total) * 100);
        return (
          <div key={seg.key} className="flex items-center justify-between gap-4">
            <span className="inline-flex items-center gap-1.5">
              <span className={`size-2 rounded-full ${seg.cls}`} />
              {t(`rum.views.dist.${seg.label}`)}
            </span>
            <span className="font-mono tabular-nums">
              {pct}% ({n})
            </span>
          </div>
        );
      })}
    </div>
  );

  return (
    <Tooltip title={tooltip}>
      <div className="flex cursor-pointer items-center gap-2">
        <div className="flex h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--color-fill-2)]">
          {SEGMENTS.map((seg) => {
            const n = dist[seg.key] || 0;
            if (n <= 0) return null;
            return <div key={seg.key} className={seg.cls} style={{ width: `${(n / total) * 100}%` }} />;
          })}
        </div>
        <span className="w-7 shrink-0 text-right text-[11px] font-medium tabular-nums text-[var(--color-text-3)]">
          {goodPct}%
        </span>
      </div>
    </Tooltip>
  );
}

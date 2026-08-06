import type { ApmServiceRedPoint } from '@/app/apm/types';
import { deriveHealth, type HealthLevel } from '@/app/apm/components/metric-format';
import type { CatalogStatus } from '@/app/apm/types';

interface MiniTrendProps {
  points?: ApmServiceRedPoint[];
  status?: CatalogStatus;
  errorRate?: number | null;
  level?: HealthLevel;
  barCount?: number;
}

const LEVEL_BAR_CLASS: Record<HealthLevel, string> = {
  1: 'bg-[var(--color-fail)]',
  2: 'bg-[var(--theme-color-status-warning)]',
  3: 'bg-[var(--theme-color-status-warning)]',
  4: 'bg-[var(--color-primary)]',
  5: 'bg-[var(--color-primary)]',
};

export default function MiniTrend({
  points = [],
  status,
  errorRate = null,
  level,
  barCount = 8,
}: MiniTrendProps) {
  const resolved = level ?? (status ? deriveHealth(status, errorRate) : 5);
  const values = points
    .map((point) => point.request_rate)
    .filter((value): value is number => value !== null && Number.isFinite(value));
  const sample = values.length
    ? values.slice(-barCount)
    : Array.from({ length: barCount }, () => 0);
  while (sample.length < barCount) sample.unshift(0);
  const max = Math.max(...sample, 1);

  return (
    <span className="inline-flex h-[22px] items-end gap-0.5" aria-hidden="true">
      {sample.map((value, index) => (
        <span
          key={index}
          className={`inline-block w-1 rounded-sm ${LEVEL_BAR_CLASS[resolved]} ${value === 0 && !values.length ? 'opacity-30' : ''}`}
          style={{ height: Math.max(4, Math.round((value / max) * 18) || 4) }}
        />
      ))}
    </span>
  );
}

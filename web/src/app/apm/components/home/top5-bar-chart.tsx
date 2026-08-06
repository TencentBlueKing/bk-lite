'use client';

import Link from 'next/link';
import type { ApmTimeWindow } from '@/app/apm/types';
import { formatLatency, formatThroughput } from '@/app/apm/components/metric-format';

export interface Top5BarRow {
  service_id: string;
  name: string;
  environment: string;
  value: number;
  sub: string;
}

interface Top5BarChartProps {
  rows: Top5BarRow[];
  valueFormatter: (v: number) => string;
  colorOf: (v: number) => string;
  subField: string;
  window: ApmTimeWindow;
}

export function errorRateBarColor(value: number): string {
  if (value >= 1) return 'var(--color-fail)';
  if (value >= 0.1) return 'var(--theme-color-status-warning)';
  return 'var(--color-success)';
}

export function p95BarColor(value: number): string {
  if (value >= 1000) return 'var(--color-fail)';
  if (value >= 300) return 'var(--theme-color-status-warning)';
  return 'var(--color-success)';
}

export function formatTopErrorSubValue(p95Ms: number | null): string {
  return formatLatency(p95Ms);
}

export function formatTopP95SubValue(requestRate: number | null): string {
  if (requestRate === null) return '—';
  return `${formatThroughput(requestRate)}/s`;
}

export default function Top5BarChart({
  rows,
  valueFormatter,
  colorOf,
  subField,
  window,
}: Top5BarChartProps) {
  const max = Math.max(...rows.map((r) => r.value), 0.0001);
  return (
    <div className="flex flex-col">
      {rows.map((row, index) => {
        const pct = (row.value / max) * 100;
        const color = colorOf(row.value);
        return (
          <div
            key={`${row.service_id}-${row.environment}`}
            className={`grid grid-cols-[120px_1fr_70px] items-center gap-3 py-2.5 ${
              index < rows.length - 1 ? 'border-b border-[var(--color-border)]' : ''
            }`}
          >
            <Link
              href={`/apm/services/${row.service_id}?environment=${encodeURIComponent(row.environment)}&window=${window}`}
              className="truncate text-[13px] font-medium text-[var(--color-text-1)] hover:text-[var(--color-primary)]"
              title={row.name}
            >
              {row.name}
            </Link>
            <div className="flex items-center gap-2">
              <div className="h-1 flex-1 overflow-hidden rounded-sm bg-[var(--color-bg-1)]">
                <div
                  className="h-full rounded-sm transition-[width] duration-200"
                  style={{ width: `${pct}%`, background: color }}
                />
              </div>
              <span className="min-w-[100px] text-right text-[11px] tabular-nums text-[var(--color-text-4)]">
                {subField} {row.sub}
              </span>
            </div>
            <span
              className="text-right text-sm font-semibold tabular-nums"
              style={{ color }}
            >
              {valueFormatter(row.value)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

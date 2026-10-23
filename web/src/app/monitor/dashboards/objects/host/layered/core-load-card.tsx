'use client';

import React from 'react';
import { HOST_PALETTE } from '../config';
import type { EntityTableRow } from '../entity-series';
import classic from '../index.module.scss';
import styles from './layered.module.scss';

const formatCorePercent = (value: number) => {
  const rounded = Math.round(value * 10) / 10;
  const text = Number.isInteger(rounded) ? rounded.toFixed(0) : rounded.toFixed(1);
  return `${text}%`;
};

const formatSpread = (value: number) => {
  const rounded = Math.round(value * 10) / 10;
  return Number.isInteger(rounded) ? rounded.toFixed(0) : rounded.toFixed(1);
};

const reading = (row: EntityTableRow, key: string) => {
  const value = row.values[key];
  return value == null || !Number.isFinite(value) ? null : value;
};

/** 分核不再画选中核折线。无 cpu 维时由调用方不渲染本卡。始终展示明细，不折叠成摘要条。 */
export default function CoreLoadCard({
  rows,
  spread
}: {
  rows: EntityTableRow[];
  spread: number | null;
}) {
  if (!rows.length || spread == null) return null;
  const spreadText = formatSpread(spread);
  return (
    <section className={`${classic.panel} ${styles.chartPanel}`}>
      <div className={styles.chartHead}>
        <div className={styles.chartTitleGroup}>
          <div className={styles.chartTitle}>核负载</div>
          <div className={styles.chartReading}>{`前 ${rows.length} 个核 · 差值 ${spreadText}%`}</div>
        </div>
      </div>
      <div className="mt-1 flex flex-col gap-2">
        {rows.map((row) => {
          const p95 = reading(row, 'cpu_usage_core_p95');
          const peak = reading(row, 'cpu_usage_core_max');
          if (p95 == null) return null;
          return (
            <div
              key={row.key}
              className="grid grid-cols-[64px_minmax(0,1fr)_auto] items-center gap-2 text-[12px]"
            >
              <span className="truncate text-[var(--color-text-1)]">{row.labels.cpu}</span>
              <span className="h-2 overflow-hidden rounded-sm bg-[var(--color-fill-2)]">
                <span
                  className="block h-full rounded-sm"
                  style={{
                    width: `${Math.min(100, Math.max(0, p95))}%`,
                    background: HOST_PALETTE.blue
                  }}
                />
              </span>
              <span className="tabular-nums text-[var(--color-text-3)]">
                {formatCorePercent(p95)}
                {peak != null ? ` · 最高 ${formatCorePercent(peak)}` : ''}
              </span>
            </div>
          );
        })}
      </div>
      <table className="mt-3 w-full border-collapse text-[12px]">
        <thead>
          <tr className="text-left font-medium text-[var(--color-text-3)]">
            <th className="border-b border-[var(--color-border)] px-1 py-1">核</th>
            <th className="border-b border-[var(--color-border)] px-1 py-1">使用率</th>
            <th className="border-b border-[var(--color-border)] px-1 py-1">最高</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const p95 = reading(row, 'cpu_usage_core_p95');
            const peak = reading(row, 'cpu_usage_core_max');
            if (p95 == null) return null;
            return (
              <tr key={row.key}>
                <td className="border-b border-[var(--color-fill-2)] px-1 py-1">{row.labels.cpu}</td>
                <td className="border-b border-[var(--color-fill-2)] px-1 py-1 tabular-nums">{formatCorePercent(p95)}</td>
                <td className="border-b border-[var(--color-fill-2)] px-1 py-1 tabular-nums">
                  {peak == null ? '—' : formatCorePercent(peak)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

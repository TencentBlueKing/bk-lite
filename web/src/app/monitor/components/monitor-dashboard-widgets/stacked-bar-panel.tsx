'use client';

import React from 'react';
import type { GuideItem } from '@/app/monitor/components/monitor-dashboard-widgets/types';
import {
  TitleWithGuide,
  type GuideTooltipStyles,
} from '@/app/monitor/components/monitor-dashboard-widgets/guide-tooltip';

export interface StackedBarPanelStyles extends GuideTooltipStyles {
  panel?: string;
  panelHeader?: string;
  panelHeading?: string;
  panelTitle?: string;
  panelTitleWithGuide?: string;
  panelSubTitle?: string;
}

export interface StackedBarRow {
  label: string;
  used: number;
  requested: number;
  total: number;
  usedDisplay: string;
  requestedDisplay: string;
  totalDisplay: string;
}

export interface StackedBarPanelProps {
  title: React.ReactNode;
  subtitle?: string;
  guide?: GuideItem[];
  rows: StackedBarRow[];
  className?: string;
  styles: StackedBarPanelStyles;
}

const USED = '#2f6bff';
const REQ = 'rgba(47,107,255,0.35)';
const FREE = '#e8edf5';
const pctOf = (v: number, total: number) =>
  total > 0 ? Math.min((Math.max(v, 0) / total) * 100, 100) : 0;

const LegendDot = ({ color, text }: { color: string; text: string }) => (
  <span className="inline-flex items-center gap-1 text-xs text-[var(--color-text-3)]">
    <span className="h-2.5 w-2.5 rounded-[3px]" style={{ background: color }} />
    {text}
  </span>
);

export const StackedBarPanel = ({
  title,
  subtitle,
  guide,
  rows,
  className,
  styles,
}: StackedBarPanelProps) => (
  <div className={[styles.panel, className].filter(Boolean).join(' ')}>
    <div className={styles.panelHeader}>
      <div className={styles.panelHeading}>
        <h3 className={styles.panelTitle}>
          {guide ? (
            <TitleWithGuide
              title={title}
              items={guide}
              className={styles.panelTitleWithGuide}
              styles={styles}
            />
          ) : (
            title
          )}
        </h3>
        {subtitle ? <div className={styles.panelSubTitle}>{subtitle}</div> : null}
      </div>
    </div>
    <div className="my-1.5 mb-3 flex gap-4">
      <LegendDot color={USED} text="已用" />
      <LegendDot color={REQ} text="已请求" />
      <LegendDot color={FREE} text="余量" />
    </div>
    <div className="flex flex-col gap-3.5">
      {rows.map((r) => {
        const usedPct = pctOf(r.used, r.total);
        const reqExtraPct = pctOf(Math.max(r.requested - r.used, 0), r.total);
        const oversold = r.requested > r.total && r.total > 0;
        return (
          <div key={r.label}>
            <div className="mb-1 flex justify-between text-xs">
              <span className="font-semibold text-[var(--color-text-1)]">{r.label}</span>
              <span className="tabular-nums text-[var(--color-text-3)]">
                已用 {r.usedDisplay} / 请求 {r.requestedDisplay} / 可分配 {r.totalDisplay}
              </span>
            </div>
            <div
              className={`flex h-3.5 overflow-hidden rounded-[7px]${oversold ? ' shadow-[inset_0_0_0_1.5px_var(--color-fail)]' : ''}`}
              style={{ background: FREE }}
            >
              <div style={{ width: `${usedPct}%`, background: USED }} />
              <div style={{ width: `${reqExtraPct}%`, background: REQ }} />
            </div>
            {oversold ? (
              <div className="mt-0.5 text-[11px] text-[var(--color-fail)]">
                请求已超卖
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  </div>
);

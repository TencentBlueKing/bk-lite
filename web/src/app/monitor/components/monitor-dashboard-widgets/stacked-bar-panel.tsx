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
  <span
    style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 4,
      fontSize: 12,
      color: '#5b6577',
    }}
  >
    <span style={{ width: 10, height: 10, borderRadius: 3, background: color }} />
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
    <div style={{ display: 'flex', gap: 16, margin: '6px 0 12px' }}>
      <LegendDot color={USED} text="已用" />
      <LegendDot color={REQ} text="已请求" />
      <LegendDot color={FREE} text="余量" />
    </div>
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {rows.map((r) => {
        const usedPct = pctOf(r.used, r.total);
        const reqExtraPct = pctOf(Math.max(r.requested - r.used, 0), r.total);
        const oversold = r.requested > r.total && r.total > 0;
        return (
          <div key={r.label}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                fontSize: 12,
                marginBottom: 4,
              }}
            >
              <span style={{ fontWeight: 600, color: '#1f2733' }}>{r.label}</span>
              <span style={{ color: '#5b6577', fontVariantNumeric: 'tabular-nums' }}>
                已用 {r.usedDisplay} / 请求 {r.requestedDisplay} / 可分配 {r.totalDisplay}
              </span>
            </div>
            <div
              style={{
                display: 'flex',
                height: 14,
                borderRadius: 7,
                overflow: 'hidden',
                background: FREE,
                boxShadow: oversold ? 'inset 0 0 0 1.5px #ff4d4f' : undefined,
              }}
            >
              <div style={{ width: `${usedPct}%`, background: USED }} />
              <div style={{ width: `${reqExtraPct}%`, background: REQ }} />
            </div>
            {oversold ? (
              <div style={{ fontSize: 11, color: '#ff4d4f', marginTop: 2 }}>
                请求已超卖
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  </div>
);

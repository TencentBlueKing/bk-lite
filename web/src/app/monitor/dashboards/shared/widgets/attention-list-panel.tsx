'use client';

import React from 'react';
import { GuideItem } from '../types';
import { TitleWithGuide, GuideTooltipStyles } from './guide-tooltip';

export interface AttentionListPanelStyles extends GuideTooltipStyles {
  panel?: string;
  panelHeader?: string;
  panelHeading?: string;
  panelTitle?: string;
  panelTitleWithGuide?: string;
  panelSubTitle?: string;
}

export interface AttentionItem {
  pod: string;
  namespace: string;
  reason: string;
  tone: 'error' | 'warning';
}

export interface AttentionListPanelProps {
  title: React.ReactNode;
  subtitle?: string;
  guide?: GuideItem[];
  items: AttentionItem[];
  emptyText?: string;
  /** 最多展示行数;超出显示「等 N 个」。默认 12。 */
  maxRows?: number;
  className?: string;
  styles: AttentionListPanelStyles;
}

const TONE_COLOR = { error: '#ff4d4f', warning: '#faad14' };

export const AttentionListPanel = ({
  title,
  subtitle,
  guide,
  items,
  emptyText = '暂无异常 Pod',
  maxRows = 12,
  className,
  styles
}: AttentionListPanelProps) => {
  const shown = items.slice(0, maxRows);
  const overflow = items.length - shown.length;
  return (
    <div className={[styles.panel, className].filter(Boolean).join(' ')}>
      <div className={styles.panelHeader}>
        <div className={styles.panelHeading}>
          <h3 className={styles.panelTitle}>
            {guide ? (
              <TitleWithGuide title={title} items={guide} className={styles.panelTitleWithGuide} styles={styles} />
            ) : (
              title
            )}
          </h3>
          {subtitle ? <div className={styles.panelSubTitle}>{subtitle}</div> : null}
        </div>
      </div>
      {items.length === 0 ? (
        <div style={{ padding: '24px 0', textAlign: 'center', color: '#27c274', fontSize: 13, fontWeight: 600 }}>
          ✓ {emptyText}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 8 }}>
          {shown.map((it) => (
            <div
              key={`${it.namespace}/${it.pod}`}
              style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}
            >
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: TONE_COLOR[it.tone], flexShrink: 0 }} />
              <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: 600, color: '#1f2733' }}>
                {it.pod}
              </span>
              <span style={{ flexShrink: 0, fontSize: 11, padding: '1px 6px', borderRadius: 4, background: '#eef1f6', color: '#5b6577' }}>
                {it.namespace}
              </span>
              <span style={{ flexShrink: 0, fontSize: 12, color: TONE_COLOR[it.tone], fontWeight: 600 }}>{it.reason}</span>
            </div>
          ))}
          {overflow > 0 ? (
            <div style={{ fontSize: 12, color: '#98a2b3', paddingTop: 2 }}>等 {overflow} 个</div>
          ) : null}
        </div>
      )}
    </div>
  );
};

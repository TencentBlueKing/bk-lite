'use client';

import React from 'react';
import { GuideItem } from '../types';
import { TitleWithGuide, GuideTooltipStyles } from './guide-tooltip';

export interface StatusGridPanelStyles extends GuideTooltipStyles {
  panel?: string;
  panelHeader?: string;
  panelHeading?: string;
  panelTitle?: string;
  panelTitleWithGuide?: string;
  panelSubTitle?: string;
}

export interface StatusGridItem {
  label: string;
  value: number;
  color: string;
  alert?: boolean;
}

export interface StatusGridPanelProps {
  title: React.ReactNode;
  subtitle?: string;
  guide?: GuideItem[];
  items: StatusGridItem[];
  valueSuffix?: string;
  emptyText?: string;
  className?: string;
  styles: StatusGridPanelStyles;
}

export const StatusGridPanel = ({
  title,
  subtitle,
  guide,
  items,
  valueSuffix = '',
  emptyText = '暂无数据',
  className,
  styles
}: StatusGridPanelProps) => (
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
      <div style={{ padding: '24px 0', textAlign: 'center', color: '#98a2b3', fontSize: 13 }}>{emptyText}</div>
    ) : (
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(56px, 1fr))', gap: 8, marginTop: 8 }}>
        {items.map((it) => (
          <div
            key={it.label}
            title={`${it.label} ${it.value}${valueSuffix}`}
            style={{
              height: 44,
              borderRadius: 8,
              background: it.color,
              color: '#fff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 11,
              fontWeight: 600,
              padding: '0 4px',
              overflow: 'hidden',
              boxShadow: it.alert ? 'inset 0 0 0 2px #ff4d4f' : undefined
            }}
          >
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{it.label}</span>
          </div>
        ))}
      </div>
    )}
  </div>
);

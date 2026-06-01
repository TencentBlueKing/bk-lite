'use client';

import React from 'react';
import { GuideItem } from '../types';
import { TitleWithGuide, GuideTooltipStyles } from './guide-tooltip';

export interface HorizontalBarPanelStyles extends GuideTooltipStyles {
  panel?: string;
  panelHeader?: string;
  panelHeading?: string;
  panelTitle?: string;
  panelTitleWithGuide?: string;
  panelSubTitle?: string;
  bars?: string;
  compactBars?: string;
  barsFull?: string;
  barRow?: string;
  barLabel?: string;
  barTrack?: string;
  barFill?: string;
  barValue?: string;
}

export interface BarItem {
  label: string;
  value: number;
  display: string;
  color: string;
  max: number;
}

export interface HorizontalBarPanelProps {
  title: React.ReactNode;
  subtitle?: string;
  guide?: GuideItem[];
  items: BarItem[];
  className?: string;
  styles: HorizontalBarPanelStyles;
}

export const HorizontalBarPanel = ({
  title,
  subtitle,
  guide,
  items,
  className,
  styles
}: HorizontalBarPanelProps) => {
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
      <div className={`${styles.bars} ${styles.compactBars} ${styles.barsFull}`}>
        {items.map((item) => (
          <div key={item.label} className={styles.barRow}>
            <div className={styles.barLabel}>{item.label}</div>
            <div className={styles.barTrack}>
              <div
                className={styles.barFill}
                style={{ width: `${Math.min((item.value / item.max) * 100, 100)}%`, background: item.color }}
              />
            </div>
            <div className={styles.barValue}>{item.display}</div>
          </div>
        ))}
      </div>
    </div>
  );
};

'use client';

import React from 'react';
import { GuideItem } from '../types';
import { TitleWithGuide, GuideTooltipStyles } from './guide-tooltip';

export type StatusTone = 'ok' | 'alarm' | 'unknown';

export interface StatusListPanelStyles extends GuideTooltipStyles {
  panel?: string;
  panelHeader?: string;
  panelHeading?: string;
  panelTitle?: string;
  panelTitleWithGuide?: string;
  panelSubTitle?: string;
  statusList?: string;
  statusRow?: string;
  statusRowOk?: string;
  statusRowAlarm?: string;
  statusRowUnknown?: string;
  statusMain?: string;
  statusDot?: string;
  statusDotOk?: string;
  statusDotAlarm?: string;
  statusDotUnknown?: string;
  statusLabel?: string;
  statusBadge?: string;
  statusBadgeOk?: string;
  statusBadgeAlarm?: string;
  statusBadgeUnknown?: string;
}

export interface StatusItem {
  label: string;
  state: string;
  tone: StatusTone;
}

export interface StatusListPanelProps {
  title: React.ReactNode;
  subtitle?: string;
  guide?: GuideItem[];
  items: StatusItem[];
  className?: string;
  styles: StatusListPanelStyles;
}

const toneSuffix = (tone: StatusTone): 'Ok' | 'Alarm' | 'Unknown' =>
  tone === 'ok' ? 'Ok' : tone === 'alarm' ? 'Alarm' : 'Unknown';

export const StatusListPanel = ({
  title,
  subtitle,
  guide,
  items,
  className,
  styles
}: StatusListPanelProps) => {
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
      <div className={styles.statusList}>
        {items.map((item) => {
          const suffix = toneSuffix(item.tone);
          return (
            <div
              key={item.label}
              className={[styles.statusRow, styles[`statusRow${suffix}`]].filter(Boolean).join(' ')}
            >
              <span className={styles.statusMain}>
                <span className={[styles.statusDot, styles[`statusDot${suffix}`]].filter(Boolean).join(' ')} />
                <span className={styles.statusLabel}>{item.label}</span>
              </span>
              <span className={[styles.statusBadge, styles[`statusBadge${suffix}`]].filter(Boolean).join(' ')}>
                {item.state}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

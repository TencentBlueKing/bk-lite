'use client';

import React from 'react';
import type { GuideItem } from '@/app/monitor/components/monitor-dashboard-widgets/types';
import {
  TitleWithGuide,
  type GuideTooltipStyles,
} from '@/app/monitor/components/monitor-dashboard-widgets/guide-tooltip';

export interface DetailPanelStyles extends GuideTooltipStyles {
  panel?: string;
  detailCard?: string;
  panelHeading?: string;
  panelTitle?: string;
  panelTitleWithGuide?: string;
  panelSubTitle?: string;
  detailRowsFill?: string;
}

export interface DetailPanelProps {
  title: React.ReactNode;
  subtitle?: string;
  guide?: GuideItem[];
  className?: string;
  bodyClassName?: string;
  styles: DetailPanelStyles;
  children: React.ReactNode;
}

export const DetailPanel = ({
  title,
  subtitle,
  guide,
  className,
  bodyClassName,
  styles,
  children,
}: DetailPanelProps) => {
  return (
    <div className={[styles.panel, className].filter(Boolean).join(' ')}>
      <div className={[styles.detailCard, bodyClassName].filter(Boolean).join(' ')}>
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
        <div className={styles.detailRowsFill}>{children}</div>
      </div>
    </div>
  );
};

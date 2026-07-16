'use client';

import React from 'react';
import type { GuideItem } from '@/components/monitor-dashboard-widgets/types';
import {
  TitleWithGuide,
  type GuideTooltipStyles,
} from '@/components/monitor-dashboard-widgets/guide-tooltip';

export interface DashboardPanelStyles extends GuideTooltipStyles {
  panel?: string;
  panelHeader?: string;
  panelHeading?: string;
  panelTitle?: string;
  panelTitleWithGuide?: string;
  panelSubTitle?: string;
}

export interface DashboardPanelProps {
  title: React.ReactNode;
  subtitle?: string;
  guide?: GuideItem[];
  className?: string;
  bodyClassName?: string;
  styles: DashboardPanelStyles;
  children: React.ReactNode;
}

export const DashboardPanel = ({
  title,
  subtitle,
  guide,
  className,
  bodyClassName,
  styles,
  children,
}: DashboardPanelProps) => {
  const content = bodyClassName ? <div className={bodyClassName}>{children}</div> : children;

  return (
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
      {content}
    </div>
  );
};

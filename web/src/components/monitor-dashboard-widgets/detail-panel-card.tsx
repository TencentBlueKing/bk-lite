'use client';

import React from 'react';
import type { GuideItem } from '@/components/monitor-dashboard-widgets/types';
import {
  TitleWithGuide,
  type GuideTooltipStyles,
} from '@/components/monitor-dashboard-widgets/guide-tooltip';
import {
  DetailMetricRow,
  type DetailMetricRowProps,
  type DetailMetricRowStyles,
} from '@/components/monitor-dashboard-widgets/detail-metric-row';

export type DetailPanelCardRow = Omit<DetailMetricRowProps, 'styles'>;

export interface DetailPanelCardStyles extends DetailMetricRowStyles, GuideTooltipStyles {
  panel?: string;
  panelHeading?: string;
  panelTitle?: string;
  panelTitleWithGuide?: string;
  panelSubTitle?: string;
  detailRowsFill?: string;
  detailEmpty?: string;
}

export interface DetailPanelCardProps {
  title: React.ReactNode;
  subtitle?: string;
  guide?: GuideItem[];
  rows: DetailPanelCardRow[];
  hasData?: boolean;
  emptyText?: React.ReactNode;
  className?: string;
  styles: DetailPanelCardStyles;
}

export const DetailPanelCard = ({
  title,
  subtitle,
  guide,
  rows,
  hasData = rows.length > 0,
  emptyText = '当前时间范围内暂无可展示详情',
  className,
  styles,
}: DetailPanelCardProps) => {
  return (
    <div className={[styles.panel, className].filter(Boolean).join(' ')}>
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
      {hasData ? (
        <div className={styles.detailRowsFill}>
          {rows.map((row) => (
            <DetailMetricRow
              key={String(row.label)}
              label={row.label}
              value={row.value}
              viz={row.viz}
              trend={row.trend}
              barValue={row.barValue}
              tone={row.tone}
              statusColor={row.statusColor}
              color={row.color}
              guide={row.guide}
              styles={styles}
            />
          ))}
        </div>
      ) : (
        <div className={styles.detailEmpty}>{emptyText}</div>
      )}
    </div>
  );
};

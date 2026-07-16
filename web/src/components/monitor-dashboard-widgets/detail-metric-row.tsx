'use client';

import React from 'react';
import type { ChartData, GuideItem } from '@/components/monitor-dashboard-widgets/types';
import {
  MiniTrendChart,
  type MiniTrendChartStyles,
} from '@/components/monitor-dashboard-widgets/mini-trend-chart';
import {
  TitleWithGuide,
  type GuideTooltipStyles,
} from '@/components/monitor-dashboard-widgets/guide-tooltip';

const DETAIL_TONE_COLORS = {
  normal: '#2f6bff',
  warning: '#faad14',
  error: '#ff4d4f',
} as const;

export type DetailRowViz = 'spark' | 'bar' | 'none';

export interface DetailMetricRowStyles extends MiniTrendChartStyles, GuideTooltipStyles {
  detailMetricRow?: string;
  detailMetricLabel?: string;
  detailRowViz?: string;
  detailBar?: string;
  detailBarFill?: string;
  detailMetricValue?: string;
  detailStatusDot?: string;
}

export interface DetailMetricRowProps {
  label: React.ReactNode;
  value: React.ReactNode;
  viz?: DetailRowViz;
  trend?: ChartData[];
  barValue?: number;
  tone?: 'error' | 'warning' | 'normal';
  statusColor?: string;
  color?: string;
  guide?: GuideItem[];
  styles: DetailMetricRowStyles;
}

export const DetailMetricRow = ({
  label,
  value,
  viz = 'none',
  trend = [],
  barValue = 0,
  tone = 'normal',
  statusColor,
  color,
  guide,
  styles,
}: DetailMetricRowProps) => {
  const toneColor = DETAIL_TONE_COLORS[tone];
  const vizColor = color ?? toneColor;
  const valueColor = statusColor ?? (tone === 'normal' ? undefined : toneColor);

  return (
    <div className={styles.detailMetricRow}>
      {guide && guide.length > 0 ? (
        <TitleWithGuide title={label} items={guide} className={styles.detailMetricLabel} styles={styles} />
      ) : (
        <span className={styles.detailMetricLabel}>{label}</span>
      )}
      <span className={styles.detailRowViz}>
        {viz === 'spark' && <MiniTrendChart data={trend} color={vizColor} styles={styles} />}
        {viz === 'bar' && (
          <span className={styles.detailBar}>
            <span className={styles.detailBarFill} style={{ width: `${barValue}%`, background: vizColor }} />
          </span>
        )}
      </span>
      <span className={styles.detailMetricValue} style={valueColor ? { color: valueColor } : undefined}>
        {statusColor && <span className={styles.detailStatusDot} style={{ background: statusColor }} />}
        {value}
      </span>
    </div>
  );
};

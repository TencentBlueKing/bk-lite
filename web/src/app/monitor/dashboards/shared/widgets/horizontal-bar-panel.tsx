'use client';

import React from 'react';
import { GuideItem } from '../types';
import { ChartData } from '@/app/monitor/types';
import { TitleWithGuide, GuideTooltipStyles } from './guide-tooltip';
import { MiniTrendChart } from './mini-trend-chart';

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
  barsTrend?: string;
  barRow?: string;
  barLabel?: string;
  barTrack?: string;
  barFill?: string;
  barSpark?: string;
  barValue?: string;
  miniTrendPlaceholder?: string;
}

export interface BarItem {
  label: string;
  value: number;
  display: string;
  color: string;
  max: number;
  /** 提供时间序列则渲染 sparkline 趋势(替代静态进度条);不提供则保留进度条。 */
  trend?: ChartData[];
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
  // 趋势(sparkline)面板让缩略图横向撑满，填满面板宽度、趋势更可读；
  // 进度条(分布/对比)面板保持固定窄列。
  const isTrendPanel = items.some((item) => item.trend && item.trend.length > 0);
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
      <div className={`${styles.bars} ${styles.compactBars} ${styles.barsFull} ${isTrendPanel ? styles.barsTrend || '' : ''}`}>
        {items.map((item) => (
          <div key={item.label} className={styles.barRow}>
            <div className={styles.barLabel}>{item.label}</div>
            {item.trend && item.trend.length > 0 ? (
              <div className={styles.barSpark}>
                <MiniTrendChart data={item.trend} color={item.color} styles={styles} />
              </div>
            ) : (
              <div className={styles.barTrack}>
                <div
                  className={styles.barFill}
                  style={{ width: `${Math.min((item.value / item.max) * 100, 100)}%`, background: item.color }}
                />
              </div>
            )}
            <div className={styles.barValue}>{item.display}</div>
          </div>
        ))}
      </div>
    </div>
  );
};

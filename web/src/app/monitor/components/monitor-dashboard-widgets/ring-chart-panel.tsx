'use client';

import React, { useMemo } from 'react';
import type { GuideItem } from '@/app/monitor/components/monitor-dashboard-widgets/types';
import ChartEmptyState from '@/components/chart-empty-state';
import {
  TitleWithGuide,
  type GuideTooltipStyles,
} from '@/app/monitor/components/monitor-dashboard-widgets/guide-tooltip';
import { useECharts } from '@/app/monitor/components/monitor-dashboard-widgets/useECharts';

export interface RingChartPanelStyles extends GuideTooltipStyles {
  panel?: string;
  panelHeader?: string;
  panelHeading?: string;
  panelTitle?: string;
  panelTitleWithGuide?: string;
  panelSubTitle?: string;
  ringCard?: string;
  ringChartWrap?: string;
  ringChartCanvas?: string;
  ringCenter?: string;
  ringCenterOverlay?: string;
  ringValue?: string;
  ringCaption?: string;
  ringInfoPanel?: string;
  metricList?: string;
  metricRow?: string;
  metricRowPercentOnly?: string;
  metricKey?: string;
  metricLabelGroup?: string;
  metricDot?: string;
  metricName?: string;
  metricValueGroup?: string;
  metricPercent?: string;
  metricCount?: string;
}

export interface RingChartDataItem {
  name: string;
  value: number;
  color: string;
  display?: string;
}

export interface RingChartInfoRow {
  name: string;
  color: string;
  primary: string;
  secondary?: string;
}

export interface RingChartPanelProps {
  title: React.ReactNode;
  subtitle?: string;
  guide?: GuideItem[];
  data: RingChartDataItem[];
  centerValue: string;
  centerCaption: string;
  infoRows?: RingChartInfoRow[];
  innerRadius?: number;
  outerRadius?: number;
  chartExtra?: React.ReactNode;
  ringCardClassName?: string;
  ringChartWrapClassName?: string;
  className?: string;
  isEmpty?: boolean;
  emptyDescription?: string;
  styles: RingChartPanelStyles;
}

export const RingChartPanel = ({
  title,
  subtitle,
  guide,
  data,
  centerValue,
  centerCaption,
  infoRows,
  innerRadius = 52,
  outerRadius = 72,
  chartExtra,
  ringCardClassName,
  ringChartWrapClassName,
  className,
  isEmpty = false,
  emptyDescription = '暂无数据',
  styles,
}: RingChartPanelProps) => {
  const total = data.reduce((sum, item) => sum + item.value, 0);

  const option = useMemo(() => {
    const chartData = data.filter((item) => item.value > 0);
    const innerPct = `${Math.round((innerRadius / outerRadius) * 100)}%`;
    const outerPct = '100%';

    return {
      animation: false,
      series: [
        {
          type: 'pie' as const,
          radius: [innerPct, outerPct],
          center: ['50%', '50%'],
          startAngle: 90,
          label: { show: false },
          itemStyle: { borderWidth: 0 },
          emphasis: { disabled: true },
          data: chartData.map((item) => ({
            value: item.value,
            name: item.name,
            itemStyle: { color: item.color },
          })),
        },
      ],
      tooltip: { show: false },
    };
  }, [data, innerRadius, outerRadius]);

  const { containerRef } = useECharts(option);

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
      <div className={ringCardClassName ? `${styles.ringCard} ${ringCardClassName}` : styles.ringCard}>
        {isEmpty ? (
          <div
            style={{
              gridColumn: '1 / -1',
              minHeight: 176,
              position: 'relative',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <div
              ref={containerRef}
              className={styles.ringChartCanvas}
              style={{ position: 'absolute', width: 1, height: 1, opacity: 0, pointerEvents: 'none' }}
            />
            <ChartEmptyState description={emptyDescription} compact />
          </div>
        ) : (
          <>
            <div
              className={
                ringChartWrapClassName
                  ? `${styles.ringChartWrap} ${ringChartWrapClassName}`
                  : styles.ringChartWrap
              }
            >
              <div ref={containerRef} className={styles.ringChartCanvas} style={{ width: '100%', height: '100%' }} />
              <div className={`${styles.ringCenter} ${styles.ringCenterOverlay}`}>
                <div className={styles.ringValue}>{centerValue}</div>
                <div className={styles.ringCaption}>{centerCaption}</div>
              </div>
              {chartExtra}
            </div>
            <div className={styles.ringInfoPanel}>
              <div className={styles.metricList}>
                {(infoRows ||
                  data.map((item) => ({
                    name: item.name,
                    color: item.color,
                    primary: `${total > 0 ? ((item.value / total) * 100).toFixed(1) : '0.0'}%`,
                    secondary: `(${
                      item.display ||
                      (Number.isInteger(item.value) || item.value >= 100
                        ? item.value.toFixed(0)
                        : item.value.toFixed(1))
                    })`,
                  }))).map((item) => (
                  <div className={`${styles.metricRow} ${styles.metricRowPercentOnly}`} key={item.name}>
                    <span className={styles.metricKey}>
                      <span className={styles.metricLabelGroup}>
                        <span className={styles.metricDot} style={{ background: item.color }} />
                        <span className={styles.metricName}>{item.name}</span>
                      </span>
                    </span>
                    <span className={styles.metricValueGroup}>
                      <span className={styles.metricPercent}>{item.primary}</span>
                      {item.secondary ? <span className={styles.metricCount}>{item.secondary}</span> : null}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

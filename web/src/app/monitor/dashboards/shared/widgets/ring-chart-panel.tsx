'use client';

import React, { useMemo } from 'react';
import { GuideItem } from '../types';
import { TitleWithGuide, GuideTooltipStyles } from './guide-tooltip';
import { useECharts } from './useECharts';

export interface RingChartPanelStyles extends GuideTooltipStyles {
  panel?: string;
  panelHeader?: string;
  panelHeading?: string;
  panelTitle?: string;
  panelTitleWithGuide?: string;
  panelSubTitle?: string;
  ringCard?: string;
  ringChartWrap?: string;
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

export interface RingChartPanelProps {
  title: React.ReactNode;
  subtitle?: string;
  guide?: GuideItem[];
  data: RingChartDataItem[];
  centerValue: string;
  centerCaption: string;
  innerRadius?: number;
  outerRadius?: number;
  className?: string;
  styles: RingChartPanelStyles;
}

export const RingChartPanel = ({
  title,
  subtitle,
  guide,
  data,
  centerValue,
  centerCaption,
  innerRadius = 52,
  outerRadius = 72,
  className,
  styles
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
            itemStyle: { color: item.color }
          }))
        }
      ],
      tooltip: { show: false }
    };
  }, [data, innerRadius, outerRadius]);

  const { containerRef } = useECharts(option);

  return (
    <div className={className}>
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
      <div className={styles.ringCard}>
        <div className={styles.ringChartWrap}>
          <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
          <div className={`${styles.ringCenter} ${styles.ringCenterOverlay}`}>
            <div className={styles.ringValue}>{centerValue}</div>
            <div className={styles.ringCaption}>{centerCaption}</div>
          </div>
        </div>
        <div className={styles.ringInfoPanel}>
          <div className={styles.metricList}>
            {data.map((item) => (
              <div className={`${styles.metricRow} ${styles.metricRowPercentOnly}`} key={item.name}>
                <span className={styles.metricKey}>
                  <span className={styles.metricLabelGroup}>
                    <span className={styles.metricDot} style={{ background: item.color }} />
                    <span className={styles.metricName}>{item.name}</span>
                  </span>
                </span>
                <span className={styles.metricValueGroup}>
                  <span className={styles.metricPercent}>
                    {total > 0 ? ((item.value / total) * 100).toFixed(1) : '0.0'}%
                  </span>
                  <span className={styles.metricCount}>({item.display || (item.value >= 100 ? item.value.toFixed(0) : item.value.toFixed(1))})</span>
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

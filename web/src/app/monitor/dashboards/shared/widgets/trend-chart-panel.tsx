'use client';

import React from 'react';
import { Dayjs } from 'dayjs';
import EChartsLineChart from './echarts-line-chart';
import { ChartData, MetricItem } from '@/app/monitor/types';
import { GuideItem, TrendLegendItem, MetricUnit } from '../types';
import { TitleWithGuide, GuideTooltipStyles } from './guide-tooltip';

export interface TrendChartPanelStyles extends GuideTooltipStyles {
  panel?: string;
  panelHeader?: string;
  panelHeading?: string;
  chartPanelHeader?: string;
  panelTitle?: string;
  chartHeaderTitle?: string;
  panelTitleWithGuide?: string;
  panelSubTitle?: string;
  chartHeaderSubTitle?: string;
  chartLegend?: string;
  chartLegendHeader?: string;
  chartLegendItem?: string;
  chartLegendDot?: string;
  chartLegendDash?: string;
  chartWrap?: string;
}

export interface TrendChartPanelProps {
  title: React.ReactNode;
  subtitle?: string;
  guide?: GuideItem[];
  legends: TrendLegendItem[];
  data: ChartData[];
  metric: MetricItem;
  unit: MetricUnit;
  loading?: boolean;
  seriesStyles?: Array<{
    color: string;
    fillOpacity?: number;
    strokeOpacity?: number;
    strokeWidth?: number;
    strokeDasharray?: string;
    unit?: MetricUnit;
  }>;
  xAxisTimeFormat?: string;
  leftAxisWidthOverride?: number;
  allowSelect?: boolean;
  onXRangeChange?: (range: [Dayjs, Dayjs]) => void;
  bodyTop?: React.ReactNode;
  bodyBottom?: React.ReactNode;
  chartWrapClassName?: string;
  className?: string;
  styles: TrendChartPanelStyles;
}

export const TrendChartPanel = ({
  title,
  subtitle,
  guide,
  legends,
  data,
  metric,
  unit,
  loading = false,
  seriesStyles,
  xAxisTimeFormat = 'HH:mm',
  leftAxisWidthOverride = 44,
  allowSelect = false,
  onXRangeChange,
  bodyTop,
  bodyBottom,
  chartWrapClassName,
  className,
  styles
}: TrendChartPanelProps) => {
  const computedSeriesStyles = seriesStyles || legends.map((item) => ({
    color: item.color,
    fillOpacity: item.primary ? 0.08 : 0.03,
    strokeOpacity: item.primary ? 1 : 0.68,
    strokeWidth: item.primary ? 2.8 : 2.2
  }));

  return (
    <div className={[styles.panel, className].filter(Boolean).join(' ')}>
      <div className={`${styles.panelHeader} ${styles.chartPanelHeader}`}>
        <div className={styles.panelHeading}>
          <h3 className={`${styles.panelTitle} ${styles.chartHeaderTitle}`}>
            {guide ? (
              <TitleWithGuide title={title} items={guide} className={styles.panelTitleWithGuide} styles={styles} />
            ) : (
              title
            )}
          </h3>
          {subtitle ? <div className={`${styles.panelSubTitle} ${styles.chartHeaderSubTitle}`}>{subtitle}</div> : null}
        </div>
        <div className={`${styles.chartLegend} ${styles.chartLegendHeader}`}>
          {legends.map((item) => (
            <span className={styles.chartLegendItem} key={item.label}>
              <span
                className={`${styles.chartLegendDot} ${item.dashed ? styles.chartLegendDash : ''}`}
                style={{ background: item.dashed ? 'transparent' : item.color, borderColor: item.color }}
              />
              {item.label}
            </span>
          ))}
        </div>
      </div>
      {bodyTop}
      <div className={chartWrapClassName ? `${styles.chartWrap} ${chartWrapClassName}` : styles.chartWrap}>
        <EChartsLineChart
          data={data}
          metric={metric}
          unit={unit}
          loading={loading}
          xAxisTimeFormat={xAxisTimeFormat}
          leftAxisWidthOverride={leftAxisWidthOverride}
          seriesStyles={computedSeriesStyles}
          allowSelect={allowSelect}
          onXRangeChange={onXRangeChange}
        />
      </div>
      {bodyBottom}
    </div>
  );
};

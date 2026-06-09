'use client';

import React, { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import { GuideItem } from '../types';
import { MetricUnit } from '../types';
import { formatMetricValue } from '../utils/format';
import { TitleWithGuide, GuideTooltipStyles } from './guide-tooltip';
import { useECharts } from './useECharts';

export interface TreemapPanelStyles extends GuideTooltipStyles {
  panel?: string;
  panelHeader?: string;
  panelHeading?: string;
  panelTitle?: string;
  panelTitleWithGuide?: string;
  panelSubTitle?: string;
}

export interface TreemapDatum {
  name: string;
  value: number;
}

export interface TreemapPanelProps {
  title: React.ReactNode;
  subtitle?: string;
  guide?: GuideItem[];
  data: TreemapDatum[];
  unit: MetricUnit;
  emptyText?: string;
  className?: string;
  styles: TreemapPanelStyles;
}

const PALETTE = ['#2f6bff', '#13c2c2', '#27c274', '#9254de', '#ff8a1f', '#f5a623', '#36cfc9', '#597ef7'];

export const TreemapPanel = ({
  title,
  subtitle,
  guide,
  data,
  unit,
  emptyText = '暂无数据',
  className,
  styles
}: TreemapPanelProps) => {
  const isEmpty = !data.some((d) => d.value > 0);
  const option = useMemo<EChartsOption | null>(() => {
    if (isEmpty) return null;
    return {
      tooltip: {
        formatter: (info: any) => {
          const f = formatMetricValue(Number(info.value) || 0, unit);
          return `${info.name}: ${f.value}${f.unit}`;
        }
      },
      series: [
        {
          type: 'treemap',
          roam: false,
          nodeClick: false,
          breadcrumb: { show: false },
          width: '100%',
          height: '100%',
          itemStyle: { borderColor: '#fff', borderWidth: 2, gapWidth: 2 },
          label: { show: true, formatter: '{b}', color: '#fff', fontSize: 12 },
          data: data
            .filter((d) => d.value > 0)
            .map((d, i) => ({ name: d.name, value: d.value, itemStyle: { color: PALETTE[i % PALETTE.length] } }))
        }
      ]
    };
  }, [data, unit, isEmpty]);

  const { containerRef } = useECharts(option);

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
      {isEmpty ? (
        <div style={{ padding: '24px 0', textAlign: 'center', color: '#98a2b3', fontSize: 13 }}>{emptyText}</div>
      ) : (
        <div ref={containerRef} style={{ width: '100%', height: 220 }} />
      )}
    </div>
  );
};

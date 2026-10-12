'use client';

import React, { useMemo } from 'react';
import { useECharts } from '../../../shared/widgets/useECharts';
import { ChartData } from '@/app/monitor/types';
import { formatMetricValue } from '../../../shared/utils/format';
import type { MetricUnit } from '../../../shared/types';
import { CHART_COLORS } from '@/app/monitor/constants';
import styles from './layered.module.scss';

export interface ThinLegend {
  label: string;
  color: string;
}

interface ThinTimeSeriesProps {
  title: string;
  data: ChartData[];
  legends: ThinLegend[];
  unit?: MetricUnit;
  loading?: boolean;
}

const areaKeys = (data: ChartData[]) => {
  const keys = new Set<string>();
  data.forEach((point) => {
    Object.keys(point).forEach((key) => {
      if (key.startsWith('value')) keys.add(key);
    });
  });
  return Array.from(keys).sort();
};

export default function ThinTimeSeries({
  title,
  data,
  legends,
  unit = 'none',
  loading = false
}: ThinTimeSeriesProps) {
  const keys = useMemo(() => areaKeys(data), [data]);
  const option = useMemo(() => {
    if (!data.length || !keys.length) return null;
    return {
      animation: false,
      backgroundColor: 'transparent',
      grid: { top: 8, right: 10, bottom: 22, left: 44, containLabel: false },
      xAxis: {
        type: 'value' as const,
        min: 'dataMin' as const,
        max: 'dataMax' as const,
        axisLabel: { show: false },
        axisTick: { show: false },
        axisLine: { lineStyle: { color: '#232a38' } },
        splitLine: { show: false }
      },
      yAxis: {
        type: 'value' as const,
        axisLabel: {
          color: '#8b98a8',
          fontSize: 10,
          formatter: (value: number) => {
            const formatted = formatMetricValue(value, unit);
            return `${formatted.value}${formatted.unit || ''}`;
          }
        },
        axisTick: { show: false },
        axisLine: { show: false },
        splitLine: { lineStyle: { color: '#232a38', width: 1 } }
      },
      tooltip: { show: false },
      series: keys.map((key, index) => {
        const color = legends[index]?.color || CHART_COLORS[index % CHART_COLORS.length];
        return {
          type: 'line' as const,
          name: legends[index]?.label || key,
          showSymbol: false,
          symbol: 'none',
          smooth: 0.15,
          connectNulls: true,
          data: data.map((point) => {
            const value = point[key];
            return [point.time, typeof value === 'number' ? value : null];
          }),
          lineStyle: { width: 1.6, color }
        };
      })
    };
  }, [data, keys, legends, unit]);
  const { containerRef } = useECharts(option);

  return (
    <section className={styles.chartPanel}>
      <div className={styles.chartHead}>
        <div className={styles.chartTitle}>{title}</div>
        <div className={styles.chartLegend}>
          {legends.map((item) => (
            <span key={item.label}>
              <span className={styles.legendSwatch} style={{ background: item.color }} />
              {item.label}
            </span>
          ))}
        </div>
      </div>
      <div className={styles.chartBody}>
        {loading || !data.length ? (
          <div className={`${styles.note} flex h-full items-center`}>{loading ? '加载中' : '当前时间窗没有序列'}</div>
        ) : (
          <div ref={containerRef} className="h-full w-full" />
        )}
      </div>
    </section>
  );
}

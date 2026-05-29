'use client';

import React, { useMemo } from 'react';
import { ChartData } from '@/app/monitor/types';
import { useECharts } from './useECharts';

export interface MiniTrendChartStyles {
  miniTrendPlaceholder?: string;
}

export const MiniTrendChart = ({
  data,
  color,
  styles
}: {
  data: ChartData[];
  color: string;
  styles: MiniTrendChartStyles;
}) => {
  const chartData = useMemo(
    () =>
      data
        .map((point) => ({
          time: Number(point.time),
          value: Number(point.value1 ?? 0)
        }))
        .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.value)),
    [data]
  );

  const option = useMemo(() => {
    if (!chartData.length) return null;
    return {
      animation: false,
      grid: { top: 2, right: 0, bottom: 2, left: 0 },
      xAxis: {
        type: 'category' as const,
        show: false,
        data: chartData.map((p) => p.time)
      },
      yAxis: {
        type: 'value' as const,
        show: false
      },
      series: [
        {
          type: 'line' as const,
          data: chartData.map((p) => p.value),
          smooth: true,
          symbol: 'none',
          lineStyle: { width: 2, color },
          areaStyle: {
            color: {
              type: 'linear' as const,
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: `${color}3D` },
                { offset: 1, color: `${color}05` }
              ]
            }
          }
        }
      ],
      tooltip: { show: false }
    };
  }, [chartData, color]);

  const { containerRef } = useECharts(option);

  if (!chartData.length) {
    return <div className={styles.miniTrendPlaceholder} />;
  }

  return <div ref={containerRef} style={{ width: '100%', height: '100%' }} />;
};

'use client';

import React, { useMemo } from 'react';
import { useECharts } from './useECharts';
import { ChartData } from '@/app/monitor/types';

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

  const isSinglePoint = chartData.length === 1;
  const seriesData = useMemo(() => {
    if (!isSinglePoint) {
      return chartData.map((point) => [point.time, point.value] as [number, number]);
    }

    const point = chartData[0];
    return [
      [point.time - 1, point.value],
      [point.time, point.value],
      [point.time + 1, point.value]
    ] as Array<[number, number]>;
  }, [chartData, isSinglePoint]);
  const xAxisMin = seriesData[0]?.[0];
  const xAxisMax = seriesData[seriesData.length - 1]?.[0];

  const option = useMemo(() => {
    if (!chartData.length) return null;

    const values = chartData.map((p) => p.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const padding = (max - min) * 0.15 || 1;

    return {
      animation: false,
      grid: { top: 2, right: 0, bottom: 2, left: 0 },
      xAxis: {
        type: 'value' as const,
        show: false,
        min: xAxisMin,
        max: xAxisMax
      },
      yAxis: {
        type: 'value' as const,
        show: false,
        min: min - padding,
        max: max + padding
      },
      series: [
        {
          type: 'line' as const,
          data: seriesData,
          smooth: 0.4,
          showSymbol: isSinglePoint,
          symbol: isSinglePoint ? 'circle' : 'none',
          symbolSize: isSinglePoint ? 6 : 0,
          lineStyle: { color, width: 2 },
          areaStyle: {
            color: {
              type: 'linear' as const,
              x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: `${color}3d` },
                { offset: 1, color: `${color}05` }
              ]
            }
          }
        }
      ],
      tooltip: { show: false }
    };
  }, [chartData, color, isSinglePoint, seriesData, xAxisMax, xAxisMin]);

  const { containerRef } = useECharts(option);

  if (!chartData.length) {
    return <div className={styles.miniTrendPlaceholder} />;
  }

  return <div ref={containerRef} style={{ width: '100%', height: '100%' }} />;
};

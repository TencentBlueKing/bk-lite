'use client';

import React, { useMemo } from 'react';
import { useECharts } from './useECharts';

export interface InlineRingChartProps {
  data: Array<{ name: string; value: number; color: string }>;
  innerRadius?: number;
  outerRadius?: number;
  height?: number | string;
}

export const InlineRingChart = ({
  data,
  innerRadius = 52,
  outerRadius = 72,
  height = '100%'
}: InlineRingChartProps) => {
  const option = useMemo(() => {
    const chartData = data.filter((item) => item.value > 0);
    const innerPct = `${Math.round((innerRadius / outerRadius) * 100)}%`;

    return {
      animation: false,
      series: [
        {
          type: 'pie' as const,
          radius: [innerPct, '100%'],
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

  return <div ref={containerRef} style={{ width: '100%', height }} />;
};

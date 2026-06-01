'use client';

import React, { useId, useMemo } from 'react';
import { AreaChart, Area, ResponsiveContainer } from 'recharts';
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
  const gradientId = useId().replace(/:/g, '_');
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

  if (!chartData.length) {
    return <div className={styles.miniTrendPlaceholder} />;
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={chartData} margin={{ top: 2, right: 0, bottom: 2, left: 0 }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.24} />
            <stop offset="100%" stopColor={color} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <Area
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={2}
          fill={`url(#${gradientId})`}
          dot={false}
          activeDot={false}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
};

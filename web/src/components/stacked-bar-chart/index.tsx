import React from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import ChartEmptyState from '@/components/chart-empty-state';
import ChartSeriesTooltip from '@/components/chart-series-tooltip';

export interface StackedBarChartProps {
  data: Array<Record<string, any>>;
  colors?: Record<string, string>;
  maxBarSize?: number;
  yAxisMode?: 'segment-range' | 'stack-total';
}

const DEFAULT_COLORS = ['#F43B2C', '#D97007', '#FFAD42', '#4CAF50', '#2196F3'];

const StackedBarChart: React.FC<StackedBarChartProps> = ({
  data = [],
  colors,
  maxBarSize = 120,
  yAxisMode = 'segment-range',
}) => {
  const keys = Object.keys(data[0] || {}).filter((key) => key !== 'time');
  const allValues =
    yAxisMode === 'stack-total'
      ? data.map((item) =>
        keys
          .filter((key) => key !== 'time')
          .reduce((total, key) => total + Number(item[key] || 0), 0)
      )
      : data.flatMap((item) =>
        keys.filter((key) => key !== 'time').map((key) => Number(item[key] || 0))
      );
  const minValue = yAxisMode === 'stack-total' ? 0 : Math.min(...allValues);
  const maxValue = Math.max(...allValues);

  return data.length ? (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart
        data={data}
        margin={{
          top: 10,
        }}
      >
        <CartesianGrid strokeDasharray="3 3" vertical={false} />
        <XAxis
          dataKey="time"
          tick={{ fill: 'var(--color-text-3)', fontSize: 13 }}
        />
        <YAxis
          tick={{ fill: 'var(--color-text-3)', fontSize: 12 }}
          ticks={[minValue, maxValue]}
          axisLine={false}
        />
        <Tooltip
          content={(
            <ChartSeriesTooltip
              renderTitle={(label) => label as React.ReactNode}
              getItems={(payload) =>
                payload.map((entry: any, index: number) => ({
                  key: entry.dataKey ?? index,
                  color: entry.color,
                  description: entry.name,
                  value: entry.value,
                  sortValue: Number(entry.value ?? 0),
                }))
              }
            />
          )}
        />
        {keys.map((key, index) => (
          <Bar
            key={key}
            dataKey={key}
            stackId="a"
            maxBarSize={maxBarSize}
            fill={colors?.[key] || DEFAULT_COLORS[index % DEFAULT_COLORS.length]}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  ) : (
    <ChartEmptyState compact />
  );
};

export default StackedBarChart;

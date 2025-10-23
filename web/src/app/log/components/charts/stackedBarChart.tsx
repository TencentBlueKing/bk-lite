import React from 'react';
import { Empty } from 'antd';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

interface StackedBarChartProps {
  data: Array<Record<string, any>>;
  colors?: Record<string, string>;
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-[var(--color-bg-3)] p-4 shadow-sm">
        <p className="text-sm font-bold">{label}</p>
        {payload.map((entry: any, index: number) => (
          <div
            key={`tooltip-${index}`}
            className="flex items-center text-[14px]"
          >
            <span
              className="w-[10px] h-[10px] rounded-full mr-[4px]"
              style={{ background: entry.color }}
            ></span>
            <span className="mr-[10px] font-[500]">{entry.name}</span>
            <span className="text-[var(--color-text-3)]">{entry.value}</span>
          </div>
        ))}
      </div>
    );
  }
  return null;
};

const StackedBarChart: React.FC<StackedBarChartProps> = ({
  data = [],
  colors,
}) => {
  // 动态获取所有的键（除了 `name`，它是 X 轴的值）
  const keys = Object.keys(data[0] || {}).filter((key) => key !== 'time');
  // 默认颜色，如果没有在 colors 对象中找到对应的颜色，则使用这些颜色
  const defaultColors = ['#F43B2C', '#D97007', '#FFAD42', '#4CAF50', '#2196F3'];
  // 获取数据中的最大值和最小值
  const allValues = data.flatMap((item) =>
    keys
      .filter((key) => key !== 'time')
      .reduce((pre, cur) => (pre += item[cur]), 0)
  );
  const maxValue = Math.max(...allValues);

  return data?.length ? (
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
          ticks={[0, maxValue]} // 只展示最小值和最大值
          axisLine={false}
        />
        <Tooltip content={<CustomTooltip />} />
        {/* 动态生成 Bar 组件 */}
        {keys.map((key, index) => (
          <Bar
            key={key}
            dataKey={key}
            stackId="a"
            maxBarSize={80}
            fill={colors?.[key] || defaultColors[index % defaultColors.length]} // 使用自定义颜色或默认颜色
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  ) : (
    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
  );
};

export default StackedBarChart;

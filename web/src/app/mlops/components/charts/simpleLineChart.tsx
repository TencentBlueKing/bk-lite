import React, { useCallback, useMemo } from 'react';
import {
  XAxis,
  YAxis,
  AreaChart,
  ResponsiveContainer,
  CartesianGrid,
  Tooltip,
  Area,
} from 'recharts';
import { Empty } from 'antd';
import chartLineStyle from './index.module.scss';

interface StepData {
  step: number;
  value: number;
  [key: string]: any;
}

interface SimpleLineChartProps {
  data: StepData[];
  unit?: string;
}

const SimpleLineChart: React.FC<SimpleLineChartProps> = ({
  data = [],
  unit = '',
}) => {

  const getChartAreaKeys = useCallback((arr: StepData[]): string[] => {
    const keys = new Set<string>();
    
    if (!Array.isArray(arr)) {
      console.warn('getChartAreaKeys: 传入的参数不是数组', arr);
      return [];
    }
    
    arr.forEach((obj) => {
      if (obj && typeof obj === 'object') {
        Object.keys(obj).forEach((key) => {
          if (key.includes('value')) {
            keys.add(key);
          }
        });
      }
    });
    return Array.from(keys);
  }, []);

  const chartKeys = useMemo(() => getChartAreaKeys(data), [data, getChartAreaKeys]);

  const renderYAxisTick = useCallback((props: any) => {
    const { x, y, payload } = props;
    const label = String(payload.value);
    const maxLength = 6;
    return (
      <text
        x={x}
        y={y}
        textAnchor="end"
        fontSize={14}
        fill="var(--color-text-3)"
        dy={4}
      >
        {label.length > maxLength && <title>{label}</title>}
        {label.length > maxLength
          ? `${label.slice(0, maxLength - 1)}...`
          : label}
      </text>
    );
  }, []);

  const CustomTooltip = useCallback(({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-white p-2 border border-gray-300 rounded shadow-lg">
          <p className="text-sm font-medium">{`Step: ${label}`}</p>
          {payload.map((entry: any, index: number) => (
            <p key={index} className="text-sm" style={{ color: entry.color }}>
              {`${entry.dataKey}: ${entry.value}${unit ? ` ${unit}` : ''}`}
            </p>
          ))}
        </div>
      );
    }
    return null;
  }, [unit]);

  return (
    <div className="w-full h-full flex flex-col">
      {!!data.length ? (
        <ResponsiveContainer className={chartLineStyle.chart}>
          <AreaChart
            data={data}
            margin={{
              top: 10,
              right: 0,
              left: -10,
              bottom: 0,
            }}
          >
            <XAxis
              dataKey="step"
              tick={{ fill: 'var(--color-text-3)', fontSize: 14 }}
              tickFormatter={(value) => String(value)}
            />
            <YAxis 
              axisLine={false} 
              tickLine={false} 
              tick={renderYAxisTick} 
            />
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <Tooltip
              content={<CustomTooltip />}
              offset={15}
            />
            {chartKeys.map((key, index) => (
              <Area
                key={index}
                type="monotone"
                dataKey={key}
                stroke="#1976d2"
                strokeWidth={2}
                fillOpacity={0.1}
                fill="#1976d2"
                isAnimationActive={true}
                animationDuration={300}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      ) : (
        <div className={`${chartLineStyle.chart} ${chartLineStyle.noData}`}>
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
        </div>
      )}
    </div>
  )
};

export default SimpleLineChart;
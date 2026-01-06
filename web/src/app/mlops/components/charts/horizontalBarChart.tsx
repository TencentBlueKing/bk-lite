import React, { useCallback } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  ResponsiveContainer,
  Tooltip,
  CartesianGrid,
  LabelList,
} from 'recharts';
import { Empty } from 'antd';
import chartLineStyle from './index.module.scss';

interface DataItem {
  name: string;
  value: number;
  [key: string]: any;
}

interface HorizontalBarChartProps {
  data: DataItem[];
  minValue?: number;
  maxValue?: number;
  unit?: string;
}

const HorizontalBarChart: React.FC<HorizontalBarChartProps> = ({
  data = [],
  minValue = 0,
  maxValue = 100,
  unit = '',
}) => {

  // 动态精度计算函数
  const getDisplayPrecision = useCallback((value: number) => {
    if (value === 0) return 0;
    const absValue = Math.abs(value);
    
    if (absValue >= 100) return 0;      // 100+ → 整数
    if (absValue >= 10) return 1;       // 10-100 → 1位小数
    if (absValue >= 1) return 2;        // 1-10 → 2位小数
    if (absValue >= 0.01) return 3;     // 0.01-1 → 3位小数
    return 4;                           // < 0.01 → 4位小数
  }, []);

  // X轴格式化函数
  const formatXAxis = useCallback((value: number) => {
    if (Math.abs(value) >= 1000) {
      return value.toExponential(2); // 科学计数法
    } else if (Math.abs(value) < 0.01 && value !== 0) {
      return value.toExponential(2); // 很小的数用科学计数法
    } else {
      return Number(value.toFixed(getDisplayPrecision(value))).toString();
    }
  }, [getDisplayPrecision]);

  // 柱状图标签格式化函数
  const formatBarLabel = useCallback((value: number) => {
    const precision = getDisplayPrecision(value);
    return `${value.toFixed(precision)}${unit ? ` ${unit}` : ''}`;
  }, [unit, getDisplayPrecision]);

  const CustomTooltip = useCallback(({ active, payload }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-white p-2 border border-gray-300 rounded shadow-lg">
          <p className="text-sm font-medium">{payload[0].payload.name}</p>
          <p className="text-sm" style={{ color: payload[0].color }}>
            {`${payload[0].value}${unit ? ` ${unit}` : ''}`}
          </p>
        </div>
      );
    }
    return null;
  }, [unit]);

  return (
    <div className="w-full h-full flex flex-col">
      {!!data.length ? (
        <ResponsiveContainer className={chartLineStyle.chart}>
          <BarChart
            data={data}
            layout="vertical"
            margin={{
              top: 10,
              right: 10,
              left: 10,
              bottom: 0,
            }}
          >
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis 
              type="number" 
              domain={[minValue, maxValue]}
              tick={{ fill: 'var(--color-text-3)', fontSize: 14 }}
              tickFormatter={formatXAxis}
            />
            <YAxis 
              type="category"
              dataKey="name"
              hide
            />
            <Tooltip
              content={<CustomTooltip />}
              cursor={{ fill: 'rgba(25, 118, 210, 0.1)' }}
            />
            <Bar 
              dataKey="value" 
              fill="#1976d2"
              radius={[0, 8, 8, 0]}
              isAnimationActive={true}
              animationDuration={300}
              animationEasing="ease-out"
              shape={(props: any) => {
                const { x, y, width, height, value } = props;
                const radius = Math.min(8, height / 2);
                
                if (value >= 0) {
                  // 正数：右侧圆角，左侧直角
                  const path = `
                    M ${x} ${y}
                    L ${x + width - radius} ${y}
                    Q ${x + width} ${y} ${x + width} ${y + radius}
                    L ${x + width} ${y + height - radius}
                    Q ${x + width} ${y + height} ${x + width - radius} ${y + height}
                    L ${x} ${y + height}
                    Z
                  `;
                  return <path d={path} fill="#1976d2" stroke="none" />;
                } else {
                  // 负数：左侧圆角，右侧直角
                  // width是负值，所以 x + width 在左侧，x 在右侧
                  const leftX = x + width; // 左侧位置
                  const rightX = x; // 右侧位置
                  // const barWidth = Math.abs(width);
                  
                  const path = `
                    M ${leftX + radius} ${y}
                    L ${rightX} ${y}
                    L ${rightX} ${y + height}
                    L ${leftX + radius} ${y + height}
                    Q ${leftX} ${y + height} ${leftX} ${y + height - radius}
                    L ${leftX} ${y + radius}
                    Q ${leftX} ${y} ${leftX + radius} ${y}
                    Z
                  `;
                  return <path d={path} fill="#1976d2" stroke="none" />;
                }
              }}
            >
              <LabelList 
                dataKey="value"
                content={(props: any) => {
                  const { x, y, width, height, value } = props;
                  if (value === undefined || value === null) return null;
                  
                  const text = formatBarLabel(value);
                  const isPositive = value >= 0;
                  // 负数时width是负值，x + width是左端，x是右端
                  const labelX = isPositive ? x + width + 5 : x + width - 5;
                  const textAnchor = isPositive ? 'start' : 'end';
                  
                  return (
                    <text
                      x={labelX}
                      y={y + height / 2}
                      fill="#1976d2"
                      fontSize={12}
                      fontWeight={500}
                      textAnchor={textAnchor}
                      dominantBaseline="middle"
                    >
                      {text}
                    </text>
                  );
                }}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      ) : (
        <div className={`${chartLineStyle.chart} ${chartLineStyle.noData}`}>
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
        </div>
      )}
    </div>
  );
};

export default HorizontalBarChart;

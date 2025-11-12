import React, { useState, useEffect } from 'react';
import { Empty } from 'antd';
import {
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  BarChart,
  Bar,
  ResponsiveContainer,
  ReferenceArea,
} from 'recharts';
import CustomTooltip from './customTooltips';
import { useFormatTime } from '@/app/log/hooks';
import barChartStyle from './index.module.scss';
import dayjs, { Dayjs } from 'dayjs';
import { BasicBarChartProps } from '@/app/log/types';

const CustomBarChart: React.FC<BasicBarChartProps> = ({
  data,
  className = '',
  onXRangeChange,
}) => {
  const { formatTime } = useFormatTime();
  const [startX, setStartX] = useState<number | null>(null);
  const [endX, setEndX] = useState<number | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  useEffect(() => {
    const handleGlobalMouseUp = () => {
      if (isDragging) {
        handleMouseUp();
      }
    };
    window.addEventListener('mouseup', handleGlobalMouseUp);
    return () => {
      window.removeEventListener('mouseup', handleGlobalMouseUp);
    };
  }, [isDragging, startX, endX]);

  const handleMouseDown = (e: any) => {
    setStartX((pre) => e.activeLabel || pre);
    setIsDragging(true);
    document.body.style.userSelect = 'none'; // 禁用文本选择
  };

  const handleMouseMove = (e: any) => {
    if (isDragging) {
      setEndX((pre) => e.activeLabel || pre);
    }
  };

  const handleMouseUp = () => {
    setIsDragging(false);
    document.body.style.userSelect = ''; // 重新启用文本选择
    if (startX !== null && endX !== null) {
      const selectedTimeRange: [Dayjs, Dayjs] = [
        dayjs(Math.min(startX, endX)),
        dayjs(Math.max(startX, endX)),
      ];
      onXRangeChange && onXRangeChange(selectedTimeRange);
    }
    setStartX(null);
    setEndX(null);
  };

  const renderYAxisTick = (props: any) => {
    const { x, y, payload } = props;
    const label = String(payload.value);
    const maxLength = 6; // 设置标签的最大长度
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
  };

  const times = data.map((d) => d.time);
  const minTime = +new Date(Math.min(...times));
  const maxTime = +new Date(Math.max(...times));
  const allValues = data.map((d) => d.value);
  const maxValue = Math.max(...allValues);

  return (
    <div className={`flex w-full h-full ${className}`}>
      {!data?.length ? (
        <div className={`${barChartStyle.chart} ${barChartStyle.noData}`}>
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
        </div>
      ) : (
        <ResponsiveContainer className={barChartStyle.chart}>
          <BarChart
            data={data}
            margin={{
              top: 0,
              right: 0,
              left: 0,
              bottom: 0,
            }}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
          >
            <XAxis
              dataKey="time"
              tick={{ fill: 'var(--color-text-3)', fontSize: 14 }}
              tickFormatter={(tick) => formatTime(tick, minTime, maxTime)}
            />
            <YAxis
              axisLine={false}
              tickLine={false}
              domain={[0, 'auto']}
              tick={renderYAxisTick}
              ticks={[0, maxValue]} // Y轴只显示0和最大值
            />
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <Tooltip content={<CustomTooltip visible={!isDragging} />} />
            <Bar
              className="cursor-w-resize"
              dataKey="value" // 数据中的值字段为'value'
              fill="var(--color-primary)" // 柱子颜色为蓝色
              width={20}
              maxBarSize={30}
            />
            {isDragging && startX !== null && endX !== null && (
              <ReferenceArea
                x1={Math.min(startX, endX)}
                x2={Math.max(startX, endX)}
                strokeOpacity={0.3}
                fill="var(--color-fill-5)"
                className="cursor-w-resize"
              />
            )}
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
};

export default CustomBarChart;

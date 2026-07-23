import React, { useMemo } from 'react';
import dayjs, { Dayjs } from 'dayjs';
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
import ChartSurface from '@/components/chart-surface';
import { useChartDragSelection } from '@/components/chart-drag-selection/use-chart-drag-selection';

export interface TimeSeriesBarItem {
  time: number;
  [key: string]: unknown;
}

export interface TimeSeriesBarSeries {
  className?: string;
  dataKey: string;
  fill: string;
  hide?: boolean;
  maxBarSize?: number;
  width?: number;
}

export interface TimeSeriesBarChartProps<T extends TimeSeriesBarItem> {
  className?: string;
  containerClassName?: string;
  data: T[];
  emptyClassName?: string;
  gridVertical?: boolean;
  margin?: {
    top?: number;
    right?: number;
    left?: number;
    bottom?: number;
  };
  onXRangeChange?: (arr: [Dayjs, Dayjs]) => void;
  referenceAreaClassName?: string;
  referenceAreaFill?: string;
  renderTooltip?: (visible: boolean) => React.ReactElement;
  series: TimeSeriesBarSeries[];
  toRangeValue?: (label: number) => Dayjs;
  xAxisDataKey?: string;
  xAxisTickFormatter?: (tick: number, minTime: number, maxTime: number) => string;
  yAxisDomain?: [number | 'auto', number | 'auto'];
  yAxisTick?: React.ComponentProps<typeof YAxis>['tick'];
  yAxisTicks?: number[];
}

const DEFAULT_MARGIN = {
  top: 10,
  right: 0,
  left: 0,
  bottom: 0,
};

const TimeSeriesBarChart = <T extends TimeSeriesBarItem>({
  className = '',
  containerClassName = 'flex h-full w-full',
  data,
  emptyClassName,
  gridVertical = false,
  margin = DEFAULT_MARGIN,
  onXRangeChange,
  referenceAreaClassName,
  referenceAreaFill = 'rgba(0, 0, 255, 0.1)',
  renderTooltip,
  series,
  toRangeValue = (label) => dayjs(label),
  xAxisDataKey = 'time',
  xAxisTickFormatter,
  yAxisDomain,
  yAxisTick = { fill: 'var(--color-text-3)', fontSize: 14 },
  yAxisTicks,
}: TimeSeriesBarChartProps<T>) => {
  const { startX, endX, isDragging, handleMouseDown, handleMouseMove, handleMouseUp } =
    useChartDragSelection<number>({
      toRange: (start, end) => [
        toRangeValue(Math.min(start, end)),
        toRangeValue(Math.max(start, end)),
      ],
      onRangeChange: onXRangeChange,
      isValidLabel: (label): label is number => typeof label === 'number',
    });

  const { minTime, maxTime } = useMemo(() => {
    if (!data.length) {
      return { minTime: 0, maxTime: 0 };
    }

    const times = data
      .map((item) => Number(item[xAxisDataKey]))
      .filter((value) => Number.isFinite(value));

    if (!times.length) {
      return { minTime: 0, maxTime: 0 };
    }

    return {
      minTime: Math.min(...times),
      maxTime: Math.max(...times),
    };
  }, [data, xAxisDataKey]);

  return (
    <ChartSurface
      hasData={!!data.length}
      containerClassName={`${containerClassName} ${className}`.trim()}
      emptyClassName={emptyClassName}
    >
      <ResponsiveContainer className={className}>
        <BarChart
          data={data}
          margin={margin}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
        >
          <XAxis
            dataKey={xAxisDataKey}
            tick={{ fill: 'var(--color-text-3)', fontSize: 14 }}
            tickFormatter={
              xAxisTickFormatter
                ? (tick) => xAxisTickFormatter(Number(tick), minTime, maxTime)
                : undefined
            }
          />
          <YAxis
            axisLine={false}
            tickLine={false}
            domain={yAxisDomain}
            tick={yAxisTick}
            ticks={yAxisTicks}
          />
          <CartesianGrid strokeDasharray="3 3" vertical={gridVertical} />
          {renderTooltip ? <Tooltip content={renderTooltip(!isDragging)} /> : null}
          {series.map((item) => (
            <Bar
              key={item.dataKey}
              className={item.className}
              dataKey={item.dataKey}
              fill={item.fill}
              hide={item.hide}
              width={item.width}
              maxBarSize={item.maxBarSize}
            />
          ))}
          {isDragging && startX !== null && endX !== null ? (
            <ReferenceArea
              x1={Math.min(startX, endX)}
              x2={Math.max(startX, endX)}
              strokeOpacity={0.3}
              fill={referenceAreaFill}
              className={referenceAreaClassName}
            />
          ) : null}
        </BarChart>
      </ResponsiveContainer>
    </ChartSurface>
  );
};

export default TimeSeriesBarChart;

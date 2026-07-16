import React from 'react';
import dayjs, { Dayjs } from 'dayjs';
import {
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  AreaChart,
  Area,
  ResponsiveContainer,
  ReferenceArea,
  Brush,
} from 'recharts';
import { useChartDragSelection } from '@/components/chart-drag-selection/use-chart-drag-selection';

export interface TimeSeriesAreaCanvasData {
  [key: string]: unknown;
}

export interface TimeSeriesAreaSeriesConfig {
  activeDot?: React.ComponentProps<typeof Area>['activeDot'];
  dataKey: string;
  dot?: React.ComponentProps<typeof Area>['dot'];
  fill: string;
  fillOpacity?: number;
  hide?: boolean;
  isAnimationActive?: boolean;
  stroke: string;
  strokeDasharray?: string;
  strokeLinecap?: 'butt' | 'round' | 'square';
  strokeLinejoin?: 'bevel' | 'miter' | 'round';
  strokeOpacity?: number;
  strokeWidth?: number;
  type?: React.ComponentProps<typeof Area>['type'];
  yAxisId?: string;
}

interface BrushSeriesConfig {
  dataKey: string;
  dot?: React.ComponentProps<typeof Area>['dot'];
  fill: string;
  fillOpacity?: number;
  isAnimationActive?: boolean;
  stroke: string;
  type?: React.ComponentProps<typeof Area>['type'];
}

export interface TimeSeriesAreaBrushConfig {
  dataKey: string;
  endIndex: number;
  fill?: string;
  height?: number;
  onChange: (value: unknown) => void;
  series: BrushSeriesConfig[];
  startIndex: number;
  stroke?: string;
  tickFormatter?: (tick: number) => string;
  travellerWidth?: number;
}

export interface TimeSeriesAreaChartCanvasProps<T extends TimeSeriesAreaCanvasData> {
  allowSelect?: boolean;
  brush?: TimeSeriesAreaBrushConfig;
  className?: string;
  data: T[];
  gridStroke?: string;
  gridStrokeDasharray?: string;
  gridVertical?: boolean;
  margin?: {
    top?: number;
    right?: number;
    left?: number;
    bottom?: number;
  };
  onChartClick?: (value: unknown) => void;
  onXRangeChange?: (arr: [Dayjs, Dayjs]) => void;
  overlaysAfterSeries?: React.ReactNode;
  overlaysBeforeTooltip?: React.ReactNode;
  renderTooltip?: (visible: boolean) => React.ReactElement;
  requireDistinctRange?: boolean;
  selectionFill?: string;
  selectionYAxisId?: string;
  series: TimeSeriesAreaSeriesConfig[];
  syncId?: string;
  toRangeValue?: (label: number) => Dayjs;
  xAxisDataKey: string;
  xAxisDomain?: React.ComponentProps<typeof XAxis>['domain'];
  xAxisDy?: number;
  xAxisMinTickGap?: number;
  xAxisTickCount?: number;
  xAxisTickFormatter?: (tick: number) => string;
  xAxisType?: 'number' | 'category';
  yAxisAllowDataOverflow?: boolean;
  yAxisDomain?: React.ComponentProps<typeof YAxis>['domain'];
  yAxisId?: string;
  yAxisInterval?: React.ComponentProps<typeof YAxis>['interval'];
  yAxisTick?: React.ComponentProps<typeof YAxis>['tick'];
  yAxisTicks?: number[];
  yAxisWidth?: number;
}

const TimeSeriesAreaChartCanvas = <T extends TimeSeriesAreaCanvasData>({
  allowSelect = true,
  brush,
  className,
  data,
  gridStroke,
  gridStrokeDasharray = '3 3',
  gridVertical = false,
  margin,
  onChartClick,
  onXRangeChange,
  overlaysAfterSeries,
  overlaysBeforeTooltip,
  renderTooltip,
  requireDistinctRange = false,
  selectionFill = 'rgba(0, 0, 255, 0.1)',
  selectionYAxisId,
  series,
  syncId,
  toRangeValue = (label) => dayjs(label),
  xAxisDataKey,
  xAxisDomain,
  xAxisDy,
  xAxisMinTickGap,
  xAxisTickCount,
  xAxisTickFormatter,
  xAxisType,
  yAxisAllowDataOverflow,
  yAxisDomain,
  yAxisId,
  yAxisInterval,
  yAxisTick,
  yAxisTicks,
  yAxisWidth,
}: TimeSeriesAreaChartCanvasProps<T>) => {
  const { startX, endX, isDragging, handleMouseDown, handleMouseMove, handleMouseUp } =
    useChartDragSelection<number>({
      enabled: allowSelect,
      requireDistinctRange,
      toRange: (start, end) => [
        toRangeValue(Math.min(start, end)),
        toRangeValue(Math.max(start, end)),
      ],
      onRangeChange: onXRangeChange,
      isValidLabel: (label): label is number => typeof label === 'number',
    });

  return (
    <ResponsiveContainer className={className}>
      <AreaChart
        data={data}
        syncId={syncId}
        margin={margin}
        onClick={onChartClick}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
      >
        <XAxis
          dataKey={xAxisDataKey}
          type={xAxisType}
          domain={xAxisDomain}
          tick={{ fill: 'var(--color-text-3)', fontSize: 14 }}
          tickFormatter={
            xAxisTickFormatter
              ? (tick) => xAxisTickFormatter(Number(tick))
              : undefined
          }
          tickCount={xAxisTickCount}
          minTickGap={xAxisMinTickGap}
          dy={xAxisDy}
        />
        <YAxis
          yAxisId={yAxisId}
          axisLine={false}
          tickLine={false}
          tick={yAxisTick}
          domain={yAxisDomain}
          allowDataOverflow={yAxisAllowDataOverflow}
          ticks={yAxisTicks}
          interval={yAxisInterval}
          width={yAxisWidth}
        />
        <CartesianGrid
          strokeDasharray={gridStrokeDasharray}
          vertical={gridVertical}
          stroke={gridStroke}
        />
        {overlaysBeforeTooltip}
        {renderTooltip ? <Tooltip content={renderTooltip(!isDragging)} /> : null}
        {series.map((item) => (
          <Area
            key={item.dataKey}
            type={item.type}
            dataKey={item.dataKey}
            yAxisId={item.yAxisId}
            stroke={item.stroke}
            strokeDasharray={item.strokeDasharray}
            strokeOpacity={item.strokeOpacity}
            fillOpacity={item.fillOpacity}
            fill={item.fill}
            strokeWidth={item.strokeWidth}
            dot={item.dot}
            activeDot={item.activeDot}
            isAnimationActive={item.isAnimationActive}
            strokeLinecap={item.strokeLinecap}
            strokeLinejoin={item.strokeLinejoin}
            hide={item.hide}
          />
        ))}
        {overlaysAfterSeries}
        {isDragging && startX !== null && endX !== null && allowSelect ? (
          <ReferenceArea
            x1={Math.min(startX, endX)}
            x2={Math.max(startX, endX)}
            yAxisId={selectionYAxisId}
            strokeOpacity={0.3}
            fill={selectionFill}
          />
        ) : null}
        {brush ? (
          <Brush
            dataKey={brush.dataKey}
            height={brush.height}
            travellerWidth={brush.travellerWidth}
            stroke={brush.stroke}
            fill={brush.fill}
            startIndex={brush.startIndex}
            endIndex={brush.endIndex}
            onChange={brush.onChange}
            tickFormatter={
              brush.tickFormatter
                ? (tick) => brush.tickFormatter(Number(tick))
                : undefined
            }
          >
            <AreaChart data={data}>
              {brush.series.map((item) => (
                <Area
                  key={item.dataKey}
                  type={item.type}
                  dataKey={item.dataKey}
                  stroke={item.stroke}
                  fill={item.fill}
                  fillOpacity={item.fillOpacity}
                  isAnimationActive={item.isAnimationActive}
                  dot={item.dot}
                />
              ))}
            </AreaChart>
          </Brush>
        ) : null}
      </AreaChart>
    </ResponsiveContainer>
  );
};

export default TimeSeriesAreaChartCanvas;

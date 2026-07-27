import React, { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import ReactEcharts from 'echarts-for-react';
import ChartSurface, {
  type ChartSurfaceProps,
} from '@/components/chart-surface';

type TimeSeriesRow = Record<string, unknown>;
type BorderRadius = [number, number, number, number];

export interface TimeSeriesComposedChartYAxis {
  formatter?: (value: number) => string;
  minInterval?: number;
  splitLine?: boolean;
}

export interface TimeSeriesComposedChartSeries<T extends TimeSeriesRow> {
  name: string;
  type: 'bar' | 'line';
  dataKey: keyof T & string;
  color: string;
  yAxisIndex?: number;
  barMaxWidth?: number;
  barBorderRadius?: BorderRadius;
  lineWidth?: number;
  showArea?: boolean;
  smooth?: boolean;
  showSymbol?: boolean;
}

export interface TimeSeriesComposedChartProps<T extends TimeSeriesRow> {
  data: T[] | null | undefined;
  loading?: boolean;
  series: TimeSeriesComposedChartSeries<T>[];
  xDataKey?: keyof T & string;
  getXLabel?: (item: T) => string;
  yAxes?: TimeSeriesComposedChartYAxis[];
  legendVisible?: boolean;
  xAxisBoundaryGap?: boolean;
  axisLabelFontSize?: number;
  grid?: {
    top?: number;
    right?: number;
    bottom?: number;
    left?: number;
    containLabel?: boolean;
  };
  surfaceProps?: Partial<Omit<ChartSurfaceProps, 'children' | 'hasData'>>;
}

const withAlpha = (hexColor: string, alphaHex: string) => `${hexColor}${alphaHex}`;

const createVerticalBarGradient = (color: string) => ({
  type: 'linear' as const,
  x: 0,
  y: 0,
  x2: 0,
  y2: 1,
  colorStops: [
    { offset: 0, color: withAlpha(color, 'CC') },
    { offset: 1, color },
  ],
});

const createSoftLineArea = (color: string) => ({
  color: {
    type: 'linear' as const,
    x: 0,
    y: 0,
    x2: 0,
    y2: 1,
    colorStops: [
      { offset: 0, color: withAlpha(color, '1F') },
      { offset: 1, color: withAlpha(color, '03') },
    ],
  },
});

export const formatCompactAxisValue = (value: number) => {
  if (!Number.isFinite(value)) return '--';
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(0)}k`;
  return String(Math.round(value));
};

const toNumericValue = (value: unknown) => {
  const num = Number(value ?? 0);
  return Number.isFinite(num) ? num : 0;
};

const DEFAULT_LEGEND_TEXT_COLOR = 'var(--color-text-3)';
const DEFAULT_AXIS_LABEL_COLOR = 'var(--color-text-3)';
const DEFAULT_AXIS_LINE_COLOR = 'var(--color-border-2)';
const DEFAULT_SPLIT_LINE_COLOR = 'var(--color-border-1)';

const TimeSeriesComposedChart = <T extends TimeSeriesRow>({
  data,
  loading = false,
  series,
  xDataKey = '_time' as keyof T & string,
  getXLabel,
  yAxes,
  legendVisible = true,
  xAxisBoundaryGap = true,
  axisLabelFontSize = 11,
  grid,
  surfaceProps,
}: TimeSeriesComposedChartProps<T>) => {
  const sortedData = useMemo(() => {
    if (!Array.isArray(data) || data.length === 0) {
      return [];
    }

    return [...data].sort((left, right) => {
      const leftTime = new Date(String(left[xDataKey] ?? '')).getTime();
      const rightTime = new Date(String(right[xDataKey] ?? '')).getTime();
      return leftTime - rightTime;
    });
  }, [data, xDataKey]);

  const option = useMemo<EChartsOption | null>(() => {
    if (!sortedData.length || !series.length) {
      return null;
    }

    const resolvedYAxes =
      yAxes && yAxes.length > 0
        ? yAxes
        : [{ formatter: formatCompactAxisValue, minInterval: 1 }];

    return {
      animation: false,
      color: series.map((item) => item.color),
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        appendToBody: true,
        confine: false,
        textStyle: { fontSize: 12 },
      },
      legend: legendVisible
        ? {
          top: 0,
          left: 18,
          textStyle: { color: DEFAULT_LEGEND_TEXT_COLOR, fontSize: 12 },
          itemWidth: 12,
          itemHeight: 4,
          icon: 'rect',
        }
        : { show: false },
      grid: {
        top: 34,
        left: 18,
        right: 18,
        bottom: 20,
        containLabel: true,
        ...grid,
      },
      xAxis: {
        type: 'category',
        data: sortedData.map((item) =>
          getXLabel ? getXLabel(item) : String(item[xDataKey] ?? '')
        ),
        boundaryGap: xAxisBoundaryGap,
        axisLabel: {
          color: DEFAULT_AXIS_LABEL_COLOR,
          fontSize: axisLabelFontSize,
          interval: 'auto',
          hideOverlap: true,
        },
        axisLine: { lineStyle: { color: DEFAULT_AXIS_LINE_COLOR } },
        axisTick: { show: false },
      },
      yAxis: resolvedYAxes.map((axis, index) => ({
        type: 'value',
        minInterval: axis.minInterval,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: DEFAULT_AXIS_LABEL_COLOR,
          fontSize: axisLabelFontSize,
          formatter: axis.formatter || formatCompactAxisValue,
        },
        splitLine:
          index === 0 || axis.splitLine
            ? {
              show: axis.splitLine !== false,
              lineStyle: { color: DEFAULT_SPLIT_LINE_COLOR },
            }
            : { show: false },
      })),
      series: series.map((item) => {
        const color = item.color;

        if (item.type === 'bar') {
          return {
            name: item.name,
            type: 'bar',
            data: sortedData.map((row) => toNumericValue(row[item.dataKey])),
            yAxisIndex: item.yAxisIndex || 0,
            barMaxWidth: item.barMaxWidth || 12,
            itemStyle: {
              borderRadius: item.barBorderRadius || ([3, 3, 0, 0] as BorderRadius),
              color: createVerticalBarGradient(color),
            },
          };
        }

        return {
          name: item.name,
          type: 'line',
          data: sortedData.map((row) => toNumericValue(row[item.dataKey])),
          yAxisIndex: item.yAxisIndex || 0,
          smooth: item.smooth !== false,
          symbol: item.showSymbol ? 'circle' : 'none',
          lineStyle: { width: item.lineWidth || 2, color },
          areaStyle: item.showArea ? createSoftLineArea(color) : undefined,
        };
      }),
    };
  }, [
    axisLabelFontSize,
    getXLabel,
    grid,
    legendVisible,
    series,
    sortedData,
    xAxisBoundaryGap,
    xDataKey,
    yAxes,
  ]);

  const mergedSurfaceProps: Omit<ChartSurfaceProps, 'children' | 'hasData'> = {
    loading,
    containerClassName: 'h-full w-full',
    loadingClassName: 'flex h-full w-full items-center justify-center',
    emptyClassName: 'h-full w-full',
    ...surfaceProps,
  };

  return (
    <ChartSurface hasData={!!option} {...mergedSurfaceProps}>
      <ReactEcharts option={option!} style={{ height: '100%', width: '100%' }} />
    </ChartSurface>
  );
};

export default TimeSeriesComposedChart;

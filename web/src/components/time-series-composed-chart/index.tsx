import React, { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import ReactEcharts from 'echarts-for-react';
import ChartSurface, {
  type ChartSurfaceProps,
} from '@/components/chart-surface';
import useChartColors from '@/hooks/useChartColors';

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
  /** 同名堆叠组会在同一时间刻度上累加展示。 */
  stack?: string;
  /** Monitor 告警分布使用纯色柱，其他趋势柱默认保留渐变。 */
  barGradient?: boolean;
  lineWidth?: number;
  showArea?: boolean;
  areaOpacity?: number;
  smooth?: boolean;
  showSymbol?: boolean;
  /** 多序列除颜色外用线型区分；默认实线。 */
  lineType?: 'solid' | 'dashed' | 'dotted';
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

const createSoftLineArea = (color: string, opacity = 0.12) => ({
  color: {
    type: 'linear' as const,
    x: 0,
    y: 0,
    x2: 0,
    y2: 1,
    colorStops: [
      {
        offset: 0,
        color: withAlpha(
          color,
          Math.round(Math.max(0, Math.min(1, opacity)) * 255)
            .toString(16)
            .padStart(2, '0'),
        ),
      },
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
  if (value == null || value === '') return null;
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
};

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
  const chartColors = useChartColors();
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
    const hasDistinctLineTypes = series.some(
      (item) => item.type === 'line' && item.lineType && item.lineType !== 'solid',
    );

    return {
      animation: false,
      color: series.map((item) => item.color),
      tooltip: {
        trigger: 'axis',
        axisPointer: {
          type: 'cross',
          lineStyle: { color: chartColors.textTertiary, type: 'dashed' },
          crossStyle: { color: chartColors.textTertiary, type: 'dashed' },
        },
        appendToBody: true,
        confine: false,
        backgroundColor: chartColors.tooltipBg,
        borderColor: chartColors.tooltipBorder,
        textStyle: { color: chartColors.textPrimary, fontSize: 12 },
      },
      legend: legendVisible
        ? {
          top: 0,
          left: 18,
          textStyle: { color: chartColors.textTertiary, fontSize: 12 },
          itemWidth: 12,
          itemHeight: 4,
          ...(hasDistinctLineTypes ? {} : { icon: 'rect' }),
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
          color: chartColors.axisLabel,
          fontSize: axisLabelFontSize,
          interval: 'auto',
          hideOverlap: true,
        },
        axisLine: { lineStyle: { color: chartColors.axisLine } },
        axisTick: { show: false },
      },
      yAxis: resolvedYAxes.map((axis, index) => ({
        type: 'value',
        minInterval: axis.minInterval,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: chartColors.axisLabel,
          fontSize: axisLabelFontSize,
          formatter: axis.formatter || formatCompactAxisValue,
        },
        splitLine:
          index === 0 || axis.splitLine
            ? {
              show: axis.splitLine !== false,
              lineStyle: { color: chartColors.splitLine },
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
            stack: item.stack,
            barMaxWidth: item.barMaxWidth || 12,
            itemStyle: {
              borderRadius: item.barBorderRadius || ([3, 3, 0, 0] as BorderRadius),
              color: item.barGradient === false ? color : createVerticalBarGradient(color),
            },
          };
        }

        const lineType = item.lineType || 'solid';
        const symbol = item.showSymbol
          ? lineType === 'dotted'
            ? 'triangle'
            : lineType === 'dashed'
              ? 'diamond'
              : 'circle'
          : 'none';

        return {
          name: item.name,
          type: 'line',
          data: sortedData.map((row) => toNumericValue(row[item.dataKey])),
          yAxisIndex: item.yAxisIndex || 0,
          smooth: item.smooth !== false,
          symbol,
          symbolSize: item.showSymbol ? 7 : 0,
          lineStyle: { width: item.lineWidth ?? 2, color, type: lineType },
          areaStyle: item.showArea ? createSoftLineArea(color, item.areaOpacity) : undefined,
        };
      }),
    };
  }, [
    axisLabelFontSize,
    chartColors,
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

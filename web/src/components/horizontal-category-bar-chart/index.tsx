import React from 'react';
import ReactEcharts from 'echarts-for-react';
import ChartEmptyState from '@/components/chart-empty-state';

const createHorizontalBarGradient = (color: string) => ({
  type: 'linear',
  x: 0,
  y: 0,
  x2: 1,
  y2: 0,
  colorStops: [
    { offset: 0, color: `${color}66` },
    { offset: 1, color },
  ],
});

export interface HorizontalCategoryBarChartTheme {
  axisLine: string;
  splitLine: string;
  axisLabel: string;
  tooltipBg: string;
  tooltipBorder: string;
  textPrimary: string;
  textSecondary: string;
  primary: string;
}

export interface HorizontalCategoryBarChartSeries {
  name?: string;
  data: number[];
  color: string;
  showLabel?: boolean;
  labelFormatter?: (value: number) => string;
  labelPosition?: string | ((value: number) => string);
}

export interface HorizontalCategoryBarChartProps {
  categories: string[];
  series: HorizontalCategoryBarChartSeries[];
  theme: HorizontalCategoryBarChartTheme;
  loading?: boolean;
  reverse?: boolean;
  categoryLabelWidth?: number;
  categoryLabelMaxLength?: number;
  axisLabelFontSize?: number;
  valueAxisFormatter?: (value: number) => string;
  barMaxWidth?: number;
  gridTop?: number;
  gridRight?: number;
  gridBottom?: number;
  gridLeft?: number;
  showLegend?: boolean;
  legendTop?: number;
  legendRight?: number;
  valueAxisSplitNumber?: number;
  valueAxisDomain?: [number, number];
  valueLabelColor?: string;
  valueTooltipFormatter?: (value: number) => string;
  showCategoryAxis?: boolean;
  splitLineType?: 'solid' | 'dashed';
}

const HorizontalCategoryBarChart: React.FC<HorizontalCategoryBarChartProps> = ({
  categories,
  series,
  theme,
  loading = false,
  reverse = true,
  categoryLabelWidth = 120,
  categoryLabelMaxLength = 18,
  axisLabelFontSize = 11,
  valueAxisFormatter,
  barMaxWidth = 16,
  gridTop,
  gridRight = 32,
  gridBottom = 8,
  gridLeft = 8,
  showLegend,
  legendTop = 4,
  legendRight = 8,
  valueAxisSplitNumber,
  valueAxisDomain,
  valueLabelColor,
  valueTooltipFormatter,
  showCategoryAxis = true,
  splitLineType = 'dashed',
}) => {
  const hasData = categories.length > 0 && series.length > 0;

  const normalizeData = (values: number[]) => (reverse ? [...values].reverse() : values);
  const normalizedCategories = reverse ? [...categories].reverse() : categories;
  const shouldShowLegend = showLegend ?? series.length > 1;
  const resolvedGridTop = gridTop ?? (shouldShowLegend ? 28 : 8);

  const option = hasData
    ? {
      animation: false,
      tooltip: {
        trigger: 'axis',
        appendToBody: true,
        confine: false,
        backgroundColor: theme.tooltipBg,
        borderColor: theme.tooltipBorder,
        textStyle: { color: theme.textPrimary, fontSize: 12 },
        axisPointer: { type: 'shadow' },
        valueFormatter: valueTooltipFormatter,
      },
      legend: shouldShowLegend
        ? {
          top: legendTop,
          right: legendRight,
          itemWidth: 12,
          itemHeight: 12,
          textStyle: { color: theme.textSecondary, fontSize: 11 },
        }
        : undefined,
      grid: {
        left: gridLeft,
        right: gridRight,
        top: resolvedGridTop,
        bottom: gridBottom,
        containLabel: true,
      },
      xAxis: {
        type: 'value',
        min: valueAxisDomain?.[0],
        max: valueAxisDomain?.[1],
        splitNumber: valueAxisSplitNumber,
        axisLabel: {
          color: theme.axisLabel,
          fontSize: axisLabelFontSize,
          formatter: valueAxisFormatter,
        },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: theme.splitLine, type: splitLineType } },
      },
      yAxis: {
        type: 'category',
        data: normalizedCategories,
        show: showCategoryAxis,
        axisLine: showCategoryAxis
          ? { lineStyle: { color: theme.axisLine } }
          : { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: theme.axisLabel,
          fontSize: axisLabelFontSize,
          width: categoryLabelWidth,
          overflow: 'truncate',
          formatter: (value: string) =>
            value.length > categoryLabelMaxLength
              ? `${value.slice(0, Math.max(categoryLabelMaxLength - 1, 1))}…`
              : value,
        },
      },
      series: series.map((item) => {
        const labelPositionFn =
          typeof item.labelPosition === 'function' ? item.labelPosition : undefined;
        const labelPosition =
          labelPositionFn
            ? (params: { value: number }) => labelPositionFn(params.value)
            : item.labelPosition ??
              ((params: { value: number }) => (params.value >= 0 ? 'right' : 'left'));

        return {
          name: item.name,
          type: 'bar',
          data: normalizeData(item.data),
          barMaxWidth,
          itemStyle: {
            color: createHorizontalBarGradient(item.color),
            borderRadius: [0, 3, 3, 0],
          },
          emphasis: {
            itemStyle: {
              color: createHorizontalBarGradient(item.color),
            },
          },
          label: {
            show: item.showLabel ?? false,
            position: labelPosition,
            fontSize: axisLabelFontSize,
            color: valueLabelColor ?? theme.textSecondary,
            formatter: item.labelFormatter
              ? (params: { value: number }) => item.labelFormatter!(params.value)
              : undefined,
          },
        };
      }),
    }
    : null;

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div
          className="h-5 w-5 animate-spin rounded-full border-2 border-t-transparent"
          style={{
            borderColor: `${theme.primary}33`,
            borderTopColor: 'transparent',
          }}
        />
      </div>
    );
  }

  if (!option) {
    return <ChartEmptyState compact />;
  }

  return (
    <ReactEcharts
      option={option}
      style={{ height: '100%', width: '100%' }}
      opts={{ renderer: 'canvas' }}
      notMerge
    />
  );
};

export default HorizontalCategoryBarChart;

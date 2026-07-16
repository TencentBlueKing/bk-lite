import React, { useEffect, useRef, useState } from 'react';
import ReactEcharts from 'echarts-for-react';
import { ChartDataTransformer } from '@/components/log-analysis-widgets/runtime';
import type { DashboardBarChartProps } from '@/components/log-analysis-widgets/types';
import ChartLegend from '@/components/chart-legend';
import { dispatchChartLegendSelection } from '@/components/chart-legend/selection';
import ChartWithSidebarLegend from '@/components/chart-with-sidebar-legend';
import { renderEChartsTooltipCard } from '@/components/echarts-tooltip-card';
import useChartColors from '@/hooks/useChartColors';
import { createHorizontalBarGradient, createVerticalBarGradient } from '@/utils/chartStyle';
import { useTranslation } from '@/utils/i18n';

const normalizeCategoryLabel = (value: unknown) => {
  if (value === null || value === undefined) return '--';
  const text = String(value).trim();
  return text ? text : '--';
};

const LogAnalysisBar: React.FC<DashboardBarChartProps> = ({
  rawData,
  loading = false,
  config,
  onReady,
}) => {
  const [isDataReady, setIsDataReady] = useState(false);
  const [legendSelected, setLegendSelected] = useState<Record<string, boolean>>({});
  const chartRef = useRef<any>(null);
  const { t } = useTranslation();
  const colors = useChartColors();
  const chartColors = config?.barColor ? [config.barColor, ...colors.series] : colors.series;

  const transformData = (nextRawData: any) => {
    const maps = config?.displayMaps;
    if (maps?.key && maps?.value && Array.isArray(nextRawData)) {
      const mapped = nextRawData.map((item: any) => ({
        name: normalizeCategoryLabel(item[maps.key]),
        count: Number(item[maps.value]) || 0,
      }));
      return ChartDataTransformer.transformToLineBarData(mapped);
    }
    return ChartDataTransformer.transformToLineBarData(nextRawData);
  };

  const chartData = transformData(rawData);
  const isHorizontal = config?.direction === 'horizontal';

  useEffect(() => {
    const seriesNames = (chartData?.series || []).map((item: any) => item.name);
    dispatchChartLegendSelection(
      chartRef.current?.getEchartsInstance?.(),
      seriesNames,
      legendSelected,
    );
  }, [chartData?.series, legendSelected]);

  useEffect(() => {
    if (!loading) {
      const hasData = chartData && chartData.categories.length > 0;
      setIsDataReady(hasData);
      onReady?.(hasData);
    }
  }, [chartData, loading, onReady]);

  const option: any = {
    color: chartColors,
    animation: false,
    calculable: true,
    title: { show: false },
    legend: { show: false },
    toolbox: { show: false },
    tooltip: {
      trigger: 'axis',
      appendToBody: true,
      axisPointer: {
        type: 'shadow',
      },
      enterable: true,
      confine: false,
      textStyle: {
        fontSize: 12,
      },
      backgroundColor: colors.tooltipBg,
      borderColor: colors.tooltipBorder,
      formatter: function (params: any) {
        if (!params || params.length === 0) return '';
        return renderEChartsTooltipCard({
          title: params[0].axisValueLabel,
          rows: params.map((param: any, index: number) => ({
            key: `${param.seriesName || 'series'}-${index}`,
            color: param.color,
            markerShape: 'square',
            label: param.seriesName || '--',
            value: param.value ?? '--',
          })),
        });
      },
    },
    grid: {
      top: 14,
      left: 18,
      right: 24,
      bottom: 20,
      containLabel: true,
    },
    xAxis: isHorizontal
      ? {
        type: 'value',
        minInterval: 1,
        axisTick: { show: false },
        axisLine: { show: false },
        axisLabel: {
          formatter: function (value: number) {
            if (value >= 1000) return (value / 1000).toFixed(1) + 'k';
            return value.toString();
          },
          textStyle: { color: colors.axisLabel },
        },
        splitLine: {
          show: true,
          lineStyle: { color: colors.splitLine, type: 'solid' },
        },
      }
      : {
        type: 'category',
        data: chartData?.categories || [],
        nameRotate: -90,
        axisLabel: {
          margin: 15,
          textStyle: {
            color: colors.axisLabel,
            fontSize: 11,
          },
          rotate: 0,
          interval: 'auto',
          formatter: function (value: string) {
            return value;
          },
        },
        axisLine: {
          lineStyle: {
            color: colors.axisLine,
          },
        },
        axisTick: {
          show: false,
        },
        splitLine: {
          show: false,
          lineStyle: {
            color: colors.splitLine,
          },
        },
      },
    yAxis: isHorizontal
      ? {
        type: 'category',
        data: chartData?.categories || [],
        axisLabel: {
          textStyle: {
            color: colors.axisLabel,
            fontSize: 11,
          },
          formatter: function (value: string) {
            return value.length > 12 ? value.slice(0, 12) + '...' : value;
          },
        },
        axisLine: { lineStyle: { color: colors.axisLine } },
        axisTick: { show: false },
        inverse: true,
      }
      : {
        type: 'value',
        minInterval: 1,
        axisTick: {
          show: false,
        },
        axisLine: {
          show: false,
        },
        axisLabel: {
          formatter: function (value: number) {
            if (value >= 1000) {
              return (value / 1000).toFixed(1) + 'k';
            }
            return value.toString();
          },
          textStyle: {
            color: colors.axisLabel,
          },
        },
        splitLine: {
          show: true,
          lineStyle: {
            color: colors.splitLine,
            type: 'solid',
          },
        },
      },
  };

  const barRadius = isHorizontal ? [0, 3, 3, 0] : [3, 3, 0, 0];
  const barMaxWidth = isHorizontal ? 16 : 12;
  if (chartData && chartData.series) {
    option.series = chartData.series.map((item: any, index: number) => ({
      name: item.name,
      type: 'bar',
      data: item.data,
      barMaxWidth,
      itemStyle: {
        borderRadius: barRadius,
        color: isHorizontal
          ? createHorizontalBarGradient(chartColors[index % chartColors.length] || colors.primary)
          : createVerticalBarGradient(chartColors[index % chartColors.length] || colors.primary),
      },
      emphasis: {
        focus: 'series',
      },
    }));
  } else {
    option.series = [
      {
        name: '数量',
        type: 'bar',
        data: chartData && chartData.values ? chartData.values : [],
        barMaxWidth,
        itemStyle: {
          borderRadius: barRadius,
          color: isHorizontal
            ? createHorizontalBarGradient(chartColors[0] || colors.primary)
            : createVerticalBarGradient(chartColors[0] || colors.primary),
        },
        emphasis: {
          focus: 'series',
        },
      },
    ];
  }

  return (
    <ChartWithSidebarLegend
      chart={
        <ReactEcharts
          ref={chartRef}
          option={option}
          style={{ height: '100%', width: '100%' }}
        />
      }
      legend={
        <ChartLegend
          data={chartData?.series || []}
          colors={chartColors}
          variant="table"
          title={t('log.analysis.dimension')}
          onSelectionChange={setLegendSelected}
        />
      }
      legendVisible={!!(chartData?.series && chartData.series.length > 1)}
      legendMode="responsive"
      chartPaneClassName="flex-1 min-w-[200px]"
      legendPaneClassName="ml-2 h-full w-40 flex-shrink-0 min-w-0"
      surfaceProps={{
        loading,
        hasData: !!(isDataReady && chartData && chartData.categories.length > 0),
        containerClassName: 'flex h-full w-full overflow-hidden',
        loadingClassName: 'flex h-full w-full items-center justify-center',
        emptyClassName: 'flex h-full w-full items-center justify-center',
      }}
    />
  );
};

export default LogAnalysisBar;

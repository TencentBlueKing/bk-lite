import React, { useEffect, useRef, useState } from 'react';
import ReactEcharts from 'echarts-for-react';
import { ChartDataTransformer } from '@/components/log-analysis-widgets/runtime';
import ChartLegend from '@/components/chart-legend';
import { dispatchChartLegendSelection } from '@/components/chart-legend/selection';
import ChartWithSidebarLegend from '@/components/chart-with-sidebar-legend';
import useChartColors from '@/hooks/useChartColors';
import { createSoftLineArea, createVerticalBarGradient } from '@/utils/chartStyle';
import { useTranslation } from '@/utils/i18n';

export interface LogAnalysisBarLineProps {
  rawData: any;
  loading?: boolean;
  config?: any;
  onReady?: (ready: boolean) => void;
}

const LogAnalysisBarLine: React.FC<LogAnalysisBarLineProps> = ({
  rawData,
  loading = false,
  config,
  onReady,
}) => {
  const [isDataReady, setIsDataReady] = useState(false);
  const [chartInstance, setChartInstance] = useState<any>(null);
  const [legendSelected, setLegendSelected] = useState<Record<string, boolean>>({});
  const chartRef = useRef<any>(null);
  const { t } = useTranslation();
  const colors = useChartColors();
  const chartColors = colors.series;

  const chartConfig = config?.displayMaps || config;
  const chartData = ChartDataTransformer.transformToLineBarData(rawData, chartConfig);

  useEffect(() => {
    if (!loading) {
      const hasData = chartData && chartData.categories.length > 0;
      setIsDataReady(hasData);
      onReady?.(hasData);
    }
  }, [chartData, loading, onReady]);

  const barLabel = chartConfig?.barLabel || '数量';
  const lineLabel = chartConfig?.lineLabel || '趋势';

  const option: any = {
    color: chartColors,
    animation: false,
    title: { show: false },
    legend: { show: false },
    toolbox: { show: false },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      appendToBody: true,
      confine: false,
      textStyle: { fontSize: 12 },
      backgroundColor: colors.tooltipBg,
      borderColor: colors.tooltipBorder,
    },
    grid: {
      top: 10,
      left: 18,
      right: 18,
      bottom: 20,
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: chartData?.categories || [],
      axisLabel: {
        textStyle: { color: colors.axisLabel, fontSize: 11 },
        interval: 'auto',
      },
      axisLine: { lineStyle: { color: colors.axisLine } },
      axisTick: { show: false },
    },
    yAxis: [
      {
        type: 'value',
        minInterval: 1,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          formatter: (value: number) =>
            value >= 1000 ? (value / 1000).toFixed(1) + 'k' : value.toString(),
          textStyle: { color: colors.axisLabel },
        },
        splitLine: {
          lineStyle: { color: colors.splitLine, type: 'solid' },
        },
      },
      {
        type: 'value',
        minInterval: 1,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          formatter: (value: number) =>
            value >= 1000 ? (value / 1000).toFixed(1) + 'k' : value.toString(),
          textStyle: { color: colors.axisLabel },
        },
        splitLine: { show: false },
      },
    ],
    series: [],
  };

  if (chartData?.series && chartData.series.length >= 2) {
    option.series = [
      {
        name: chartData.series[0].name || barLabel,
        type: 'bar',
        data: chartData.series[0].data,
        yAxisIndex: 0,
        barMaxWidth: 12,
        itemStyle: {
          borderRadius: [3, 3, 0, 0],
          color: createVerticalBarGradient(chartColors[0]),
        },
      },
      {
        name: chartData.series[1].name || lineLabel,
        type: 'line',
        data: chartData.series[1].data,
        yAxisIndex: 1,
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 2, color: chartColors[1] },
        areaStyle: createSoftLineArea(chartColors[1]),
      },
    ];
  } else if (chartData?.values) {
    option.series = [
      {
        name: barLabel,
        type: 'bar',
        data: chartData.values,
        barMaxWidth: 12,
        itemStyle: {
          borderRadius: [3, 3, 0, 0],
          color: createVerticalBarGradient(chartColors[0]),
        },
      },
    ];
  }

  const seriesData =
    chartData?.series && chartData.series.length > 1 ? chartData.series : null;

  useEffect(() => {
    const seriesNames = (seriesData || []).map((item: any) => item.name);
    dispatchChartLegendSelection(chartInstance, seriesNames, legendSelected);
  }, [chartInstance, legendSelected, seriesData]);

  return (
    <ChartWithSidebarLegend
      chart={
        <ReactEcharts
          ref={chartRef}
          option={option}
          style={{ height: '100%', width: '100%' }}
          onChartReady={(chart: any) => setChartInstance(chart)}
        />
      }
      legend={
        <ChartLegend
          data={seriesData || []}
          colors={chartColors}
          variant="table"
          title={t('log.analysis.dimension')}
          onSelectionChange={setLegendSelected}
        />
      }
      legendVisible={!!seriesData}
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

export default LogAnalysisBarLine;

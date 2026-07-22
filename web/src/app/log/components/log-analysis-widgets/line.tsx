import React, { useEffect, useRef, useState } from 'react';
import ReactEcharts from 'echarts-for-react';
import { ChartDataTransformer } from '@/app/log/components/log-analysis-widgets/runtime';
import ChartLegend from '@/components/chart-legend';
import { dispatchChartLegendSelection } from '@/components/chart-legend/selection';
import ChartWithSidebarLegend from '@/components/chart-with-sidebar-legend';
import { renderEChartsTooltipCard } from '@/components/echarts-tooltip-card';
import useChartColors from '@/hooks/useChartColors';
import { createSoftLineArea } from '@/utils/chartStyle';
import { useTranslation } from '@/utils/i18n';

export interface LogAnalysisLineProps {
  rawData: any;
  loading?: boolean;
  config?: any;
  onReady?: (ready: boolean) => void;
}

const LogAnalysisLine: React.FC<LogAnalysisLineProps> = ({
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
  const seriesColors = colors.series;

  const transformData = (nextRawData: any) => {
    const chartConfig = config?.displayMaps || config;
    return ChartDataTransformer.transformToLineBarData(nextRawData, chartConfig);
  };

  const chartData: any = transformData(rawData);

  useEffect(() => {
    const seriesNames = (chartData?.series || []).map((item: any) => item.name);
    dispatchChartLegendSelection(chartInstance, seriesNames, legendSelected);
  }, [chartData?.series, chartInstance, legendSelected]);

  const getTooltipFieldName = () => {
    const chartConfig = config?.displayMaps || config;
    return chartConfig?.tooltipField || '告警数';
  };

  const getSeriesOptions = () => {
    const chartConfig = config?.displayMaps || config;
    const isStacked = chartConfig?.stack === 'total';

    return {
      isStacked,
      lineWidth: isStacked ? 1.5 : 1,
      areaOpacity: isStacked ? 0.18 : 0.1,
    };
  };

  useEffect(() => {
    if (!loading) {
      const hasData = chartData && chartData.categories.length > 0;
      setIsDataReady(hasData);
      onReady?.(hasData);
    }
  }, [chartData, loading, onReady]);

  const option: any = {
    color: seriesColors,
    animation: false,
    calculable: true,
    title: { show: false },
    legend: {
      show: false,
    },
    toolbox: { show: false },
    tooltip: {
      trigger: 'axis',
      appendToBody: true,
      axisPointer: {
        type: 'cross',
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
        const tooltipFieldName = getTooltipFieldName();
        return renderEChartsTooltipCard({
          title: params[0].axisValueLabel,
          rows: params.map((param: any, index: number) => ({
            key: `${param.seriesName || tooltipFieldName}-${index}`,
            color: param.color,
            markerShape: 'circle',
            label: param.seriesName || tooltipFieldName,
            value:
              param.value !== null && param.value !== undefined
                ? param.value
                : '--',
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
    xAxis: {
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
    yAxis: {
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

  const { isStacked, lineWidth, areaOpacity } = getSeriesOptions();

  if (chartData && chartData.series) {
    option.series = chartData.series.map((item: any, index: number) => ({
      name: item.name,
      type: 'line',
      data: item.data,
      ...(isStacked ? { stack: 'total' } : {}),
      smooth: true,
      symbol: 'none',
      lineStyle: {
        width: lineWidth,
      },
      areaStyle: {
        opacity: areaOpacity,
        color: createSoftLineArea(
          seriesColors[index % seriesColors.length] || colors.primary,
        ).color,
      },
      emphasis: {
        focus: 'series',
      },
    }));
  } else {
    option.series = [
      {
        name: getTooltipFieldName(),
        type: 'line',
        data: chartData && chartData.values ? chartData.values : [],
        smooth: true,
        symbol: 'none',
        lineStyle: {
          width: lineWidth,
        },
        areaStyle: {
          opacity: areaOpacity,
          color: createSoftLineArea(seriesColors[0] || colors.primary).color,
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
          onChartReady={(chart: any) => {
            setChartInstance(chart);
          }}
        />
      }
      legend={
        <ChartLegend
          data={chartData?.series || []}
          colors={seriesColors}
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

export default LogAnalysisLine;

import React, { useCallback, useEffect, useState } from 'react';
import ReactEcharts from 'echarts-for-react';
import { ChartDataTransformer } from '@/app/log/components/log-analysis-widgets/runtime';
import ChartLegend from '@/components/chart-legend';
import { dispatchChartLegendSelection } from '@/components/chart-legend/selection';
import ChartWithSidebarLegend from '@/components/chart-with-sidebar-legend';
import { renderEChartsTooltipCard } from '@/components/echarts-tooltip-card';
import useChartColors from '@/hooks/useChartColors';
import { createHorizontalBarGradient } from '@/utils/chartStyle';
import { useTranslation } from '@/utils/i18n';

export interface LogAnalysisPieProps {
  rawData: any;
  loading?: boolean;
  config?: any;
  onReady?: (ready: boolean) => void;
}

const LogAnalysisPie: React.FC<LogAnalysisPieProps> = ({
  rawData,
  loading = false,
  config,
  onReady,
}) => {
  const [isDataReady, setIsDataReady] = useState(false);
  const [chartInstance, setChartInstance] = useState<any>(null);
  const [legendSelected, setLegendSelected] = useState<Record<string, boolean>>({});
  const { t } = useTranslation();
  const colors = useChartColors();
  const chartColors = colors.series;

  const onChartReady = useCallback((instance: any) => {
    setChartInstance(instance);
  }, []);

  const transformData = (nextRawData: any) => {
    const displayMaps = config?.displayMaps;
    if (displayMaps?.key && displayMaps?.value && Array.isArray(nextRawData)) {
      const mapped = nextRawData
        .filter((item: any) => item[displayMaps.key] !== undefined)
        .map((item: any) => ({
          name: String(item[displayMaps.key]),
          value: parseFloat(item[displayMaps.value]) || 0,
        }));
      if (mapped.length > 0) {
        return mapped;
      }
    }
    return ChartDataTransformer.transformToPieData(nextRawData);
  };

  const chartData = transformData(rawData);
  const useBarChart = chartData && chartData.length > 5;

  useEffect(() => {
    const seriesNames = (chartData || []).map((item: any) => item.name);
    dispatchChartLegendSelection(chartInstance, seriesNames, legendSelected);
  }, [chartData, chartInstance, legendSelected]);

  useEffect(() => {
    if (!loading) {
      const hasData = chartData && chartData.length > 0;
      setIsDataReady(hasData);
      onReady?.(hasData);
    }
  }, [chartData, loading, onReady]);

  const sortedBarData = useBarChart
    ? [...chartData].sort((a: any, b: any) => a.value - b.value)
    : [];

  let barOption: any = null;

  if (useBarChart) {
    barOption = {
      color: chartColors,
      animation: true,
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        confine: true,
        textStyle: { fontSize: 12, color: colors.textPrimary },
        backgroundColor: colors.tooltipBg,
        borderColor: colors.tooltipBorder,
      },
      grid: {
        left: 12,
        right: 48,
        top: 8,
        bottom: 8,
        containLabel: true,
      },
      xAxis: {
        type: 'value',
        axisLabel: { fontSize: 11, color: colors.axisLabel },
        splitLine: { lineStyle: { type: 'dashed', color: colors.splitLine } },
      },
      yAxis: {
        type: 'category',
        data: sortedBarData.map((dataItem: any) => dataItem.name),
        axisLabel: {
          fontSize: 11,
          color: colors.axisLabel,
          width: 100,
          overflow: 'truncate',
          ellipsis: '...',
        },
        axisTick: { show: false },
        axisLine: { show: false },
      },
      series: [
        {
          type: 'bar',
          data: sortedBarData.map((dataItem: any, index: number) => ({
            value: dataItem.value,
            itemStyle: {
              color: createHorizontalBarGradient(
                chartColors[index % chartColors.length],
              ),
              borderRadius: [0, 3, 3, 0],
            },
          })),
          barMaxWidth: 16,
          label: {
            show: true,
            position: 'right',
            fontSize: 11,
            color: colors.textSecondary,
          },
        },
      ],
    };
  }

  const pieOption: any = {
    color: chartColors,
    animation: true,
    calculable: true,
    title: { show: false },
    tooltip: {
      trigger: 'item',
      appendToBody: true,
      enterable: true,
      confine: false,
      textStyle: {
        fontSize: 12,
        color: colors.textPrimary,
      },
      backgroundColor: colors.tooltipBg,
      borderColor: colors.tooltipBorder,
      formatter: function (params: any) {
        const percent = params.percent || 0;
        return renderEChartsTooltipCard({
          title: params.seriesName || '',
          rows: [
            {
              key: params.name,
              color: params.color,
              markerShape: 'circle',
              label: params.name || '--',
              value: `${params.value} (${percent.toFixed(1)}%)`,
            },
          ],
        });
      },
    },
    legend: {
      show: false,
    },
    series: [
      {
        name: '',
        type: 'pie',
        center: ['50%', '50%'],
        radius: ['45%', '69%'],
        avoidLabelOverlap: false,
        selectedMode: 'single',
        label: {
          show: true,
          position: 'center',
          formatter: function () {
            const total = (chartData || []).reduce(
              (sum: number, item: any) => sum + item.value,
              0,
            );
            return `{title|总数}\n{value|${total}}`;
          },
          rich: {
            title: {
              fontSize: 14,
              lineHeight: 20,
              color: colors.textSecondary,
            },
            value: {
              fontSize: 24,
              fontWeight: 'bold',
              lineHeight: 32,
              color: colors.textPrimary,
            },
          },
        },
        labelLine: {
          show: false,
          length: 10,
          length2: 15,
          smooth: true,
        },
        itemStyle: {
          borderRadius: 2,
          borderColor: colors.background,
          borderWidth: 1,
        },
        emphasis: {
          focus: 'none',
          scaleSize: 5,
        },
        data: chartData || [],
      },
    ],
  };

  const option = useBarChart ? barOption : pieOption;

  return (
    <ChartWithSidebarLegend
      chart={
        <ReactEcharts
          option={option}
          style={{ height: '100%', width: '100%' }}
          onChartReady={onChartReady}
        />
      }
      legend={
        <ChartLegend
          data={(chartData || []).map((item: any) => ({
            name: item.name,
            value: item.value,
          }))}
          colors={chartColors}
          variant="table"
          title={t('log.analysis.dimension')}
          onSelectionChange={setLegendSelected}
        />
      }
      legendVisible={!useBarChart && !!(chartData && chartData.length > 1)}
      legendMode="responsive"
      minChartWidthPx={150}
      chartPaneClassName={useBarChart ? 'w-full' : 'flex-1 min-w-[150px]'}
      legendPaneClassName="ml-2 h-full w-40 flex-shrink-0"
      surfaceProps={{
        loading,
        hasData: !!(isDataReady && chartData && chartData.length > 0),
        containerClassName: 'flex h-full w-full overflow-hidden',
        loadingClassName: 'flex h-full w-full items-center justify-center',
        emptyClassName: 'flex h-full w-full items-center justify-center',
      }}
    />
  );
};

export default LogAnalysisPie;

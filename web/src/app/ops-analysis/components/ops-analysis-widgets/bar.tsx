import React, { useCallback, useEffect, useRef, useState } from 'react';
import ReactEcharts from 'echarts-for-react';
import {
  ChartDataTransformer,
  getOpsChartTheme,
  randomColorForLegend,
  resolveOpsChartThemeName,
} from '@/app/ops-analysis/components/ops-analysis-widgets/runtime';
import type { ValueConfig } from '@/app/ops-analysis/components/ops-analysis-widgets';
import ChartLegend from '@/components/chart-legend';
import ChartWithSidebarLegend from '@/components/chart-with-sidebar-legend';
import { renderEChartsTooltipCard } from '@/components/echarts-tooltip-card';
import { useTranslation } from '@/utils/i18n';

export interface OpsAnalysisBarProps {
  rawData: any;
  loading?: boolean;
  onReady?: (ready: boolean) => void;
  config?: ValueConfig;
}

const OpsAnalysisBar: React.FC<OpsAnalysisBarProps> = ({
  rawData,
  loading = false,
  onReady,
  config,
}) => {
  const { t } = useTranslation();
  const chartRef = useRef<any>(null);
  const themeName = resolveOpsChartThemeName();
  const chartTheme = getOpsChartTheme(themeName);
  const chartColors = randomColorForLegend(themeName);
  const [legendSelected, setLegendSelected] = useState<Record<string, boolean>>({});

  const handleLegendChange = useCallback((selected: Record<string, boolean>) => {
    setLegendSelected(selected);
  }, []);

  const chartData = ChartDataTransformer.transformToLineBarData(rawData);
  const isDataReady = chartData.categories.length > 0;

  useEffect(() => {
    if (!loading) {
      onReady?.(isDataReady);
    }
  }, [isDataReady, loading, onReady]);

  const option: any = {
    color: chartColors,
    animation: false,
    calculable: true,
    title: { show: false },
    legend: { show: false, selected: legendSelected },
    toolbox: { show: false },
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'shadow',
      },
      enterable: true,
      confine: true,
      backgroundColor: 'transparent',
      borderWidth: 0,
      borderColor: 'transparent',
      extraCssText: 'box-shadow:none;padding:0;background:transparent;',
      textStyle: {
        fontSize: 12,
        color: chartTheme.tooltipTextColor,
      },
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
      top: 8,
      left: 16,
      right: 16,
      bottom: 8,
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: chartData?.categories || [],
      nameRotate: -90,
      axisLabel: {
        margin: 15,
        textStyle: {
          color: chartTheme.axisLabelColor,
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
          color: chartTheme.axisLineColor,
        },
      },
      axisTick: {
        show: false,
      },
      splitLine: {
        show: false,
        lineStyle: {
          color: chartTheme.splitLineColor,
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
          color: chartTheme.axisLabelColor,
        },
      },
      splitLine: {
        show: true,
        lineStyle: {
          color: chartTheme.splitLineColor,
          type: 'solid',
        },
      },
    },
  };

  if (chartData && chartData.series) {
    option.series = chartData.series.map((item: any) => ({
      name: item.name,
      type: 'bar',
      data: item.data,
      barMaxWidth: 40,
      ...(config?.stack ? { stack: 'total' } : {}),
      itemStyle: {
        borderRadius: [2, 2, 0, 0],
      },
      emphasis: {
        focus: 'series',
      },
    }));
  } else {
    option.series = [
      {
        name: t('topology.treeValueTitle'),
        type: 'bar',
        data: chartData && chartData.values ? chartData.values : [],
        barMaxWidth: 40,
        itemStyle: {
          borderRadius: [2, 2, 0, 0],
        },
        emphasis: {
          focus: 'series',
        },
      },
    ];
  }

  const thresholdLines = (config?.thresholdColors || [])
    .map((threshold) => ({ value: Number(threshold.value), color: threshold.color }))
    .filter((threshold) => !Number.isNaN(threshold.value) && threshold.value !== 0);
  if (thresholdLines.length > 0 && option.series.length > 0) {
    option.series[0].markLine = {
      symbol: 'none',
      silent: true,
      data: thresholdLines.map((threshold) => ({
        yAxis: threshold.value,
        lineStyle: { color: threshold.color, type: 'dashed', width: 1.5 },
        label: {
          show: true,
          position: 'insideEndTop',
          formatter: String(threshold.value),
          color: threshold.color,
          fontSize: 10,
        },
      })),
    };
  }

  const legendData = option.series.map((item: { name?: string }) => ({
    name: item.name || t('topology.treeValueTitle'),
  }));

  return (
    <ChartWithSidebarLegend
      chart={
        <ReactEcharts
          ref={chartRef}
          option={option}
          notMerge={true}
          style={{ height: '100%', width: '100%' }}
        />
      }
      legend={
        <ChartLegend
          data={legendData}
          colors={chartColors}
          layout="vertical"
          onSelectionChange={handleLegendChange}
        />
      }
      legendVisible={legendData.length > 0}
      chartPaneClassName="flex-1 min-h-0"
      surfaceProps={{
        loading,
        hasData: !!(isDataReady && chartData && chartData.categories.length > 0),
        containerClassName: 'flex h-full w-full flex-row',
        loadingClassName: 'flex h-full w-full items-center justify-center',
        emptyClassName: 'flex h-full w-full items-center justify-center',
      }}
    />
  );
};

export default OpsAnalysisBar;

import React, { useEffect, useRef, useCallback, useState } from 'react';
import ReactEcharts from 'echarts-for-react';
import { Spin, Empty } from 'antd';
import { randomColorForLegend } from '@/app/ops-analysis/utils/randomColorForChart';
import { ChartDataTransformer } from '@/app/ops-analysis/utils/chartDataTransform';
import { useTranslation } from '@/utils/i18n';
import {
  getOpsChartColorsByMode,
  getOpsChartThemeByMode,
  resolveOpsChartThemeName,
} from '@/app/ops-analysis/utils/chartTheme';
import ChartLegend from '@/app/ops-analysis/components/chartLegend';
import type {
  ScreenRenderContext,
  ValueConfig,
} from '@/app/ops-analysis/types/dashBoard';
import {
  getScreenWidgetScale,
  scaleScreenMetric,
  scaleScreenMetricFloat,
} from './shared/screenMetrics';

interface BarChartProps {
  rawData: any;
  loading?: boolean;
  onReady?: (ready: boolean) => void;
  config?: ValueConfig;
  screenRenderContext?: ScreenRenderContext;
}

const BarChart: React.FC<BarChartProps> = ({
  rawData,
  loading = false,
  onReady,
  config,
  screenRenderContext,
}) => {
  const { t } = useTranslation();
  const chartRef = useRef<any>(null);
  const themeName = resolveOpsChartThemeName();
  const usesScreenChartTheme =
    config?.chartThemeMode === 'screen-dark' ||
    config?.chartThemeMode === 'screen-light';
  const chartTheme = getOpsChartThemeByMode(config?.chartThemeMode);
  const chartColors = usesScreenChartTheme
    ? getOpsChartColorsByMode(config?.chartThemeMode, themeName)
    : randomColorForLegend(themeName);
  const widgetScale = getScreenWidgetScale(screenRenderContext);
  const [legendSelected, setLegendSelected] = useState<Record<string, boolean>>({});

  const handleLegendChange = useCallback((selected: Record<string, boolean>) => {
    setLegendSelected(selected);
  }, []);

  const transformData = (rawData: any) => {
    return ChartDataTransformer.transformToLineBarData(rawData);
  };

  const chartData = transformData(rawData);
  const isDataReady = chartData.categories.length > 0;

  useEffect(() => {
    if (!loading) {
      if (onReady) {
        onReady(isDataReady);
      }
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
      backgroundColor: chartTheme.tooltipBackgroundColor,
      borderWidth: 1,
      borderColor: chartTheme.tooltipBorderColor,
      extraCssText: `box-shadow: ${chartTheme.tooltipShadow};`,
      textStyle: {
        fontSize: scaleScreenMetric(12, screenRenderContext),
        color: chartTheme.tooltipTextColor,
      },
      formatter: function (params: any) {
        if (!params || params.length === 0) return '';
        const tooltipPaddingY = scaleScreenMetric(4, screenRenderContext);
        const tooltipPaddingX = scaleScreenMetric(8, screenRenderContext);
        const tooltipGap = scaleScreenMetric(4, screenRenderContext);
        const markerSize = scaleScreenMetric(10, screenRenderContext);
        const markerGap = scaleScreenMetric(6, screenRenderContext);
        let content = `<div style="padding: ${tooltipPaddingY}px ${tooltipPaddingX}px;">
          <div style="margin-bottom: ${tooltipGap}px; font-weight: bold;">${params[0].axisValueLabel}</div>`;

        params.forEach((param: any) => {
          content += `
            <div style="display: flex; align-items: center; margin-bottom: ${scaleScreenMetric(2, screenRenderContext)}px;">
              <span style="display: inline-block; width: ${markerSize}px; height: ${markerSize}px; background-color: ${param.color}; border-radius: ${scaleScreenMetric(2, screenRenderContext)}px; margin-right: ${markerGap}px;"></span>
              <span>${param.seriesName}: ${param.value}</span>
            </div>`;
        });

        content += '</div>';
        return content;
      },
    },
    grid: {
      top: scaleScreenMetric(8, screenRenderContext),
      left: scaleScreenMetric(16, screenRenderContext),
      right: scaleScreenMetric(16, screenRenderContext),
      bottom: scaleScreenMetric(8, screenRenderContext),
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: chartData?.categories || [],
      nameRotate: -90,
      axisLabel: {
        margin: scaleScreenMetric(15, screenRenderContext),
        textStyle: {
          color: chartTheme.axisLabelColor,
          fontSize: scaleScreenMetric(11, screenRenderContext),
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
          fontSize: scaleScreenMetric(11, screenRenderContext),
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

  // 根据数据类型设置 series
  if (chartData && chartData.series) {
    option.series = chartData.series.map((item: any) => ({
      name: item.name,
      type: 'bar',
      data: item.data,
      barMaxWidth: scaleScreenMetric(40, screenRenderContext),
      itemStyle: {
        borderRadius: usesScreenChartTheme
          ? [
            scaleScreenMetric(4, screenRenderContext),
            scaleScreenMetric(4, screenRenderContext),
            0,
            0,
          ]
          : [2, 2, 0, 0],
        shadowBlur: usesScreenChartTheme
          ? scaleScreenMetric(chartTheme.barShadowBlur, screenRenderContext)
          : 0,
        shadowColor: usesScreenChartTheme
          ? chartTheme.barShadowColor
          : 'transparent',
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
        barMaxWidth: scaleScreenMetric(40, screenRenderContext),
        itemStyle: {
          borderRadius: usesScreenChartTheme
            ? [
              scaleScreenMetric(4, screenRenderContext),
              scaleScreenMetric(4, screenRenderContext),
              0,
              0,
            ]
            : [2, 2, 0, 0],
          shadowBlur: usesScreenChartTheme
            ? scaleScreenMetric(chartTheme.barShadowBlur, screenRenderContext)
            : 0,
          shadowColor: usesScreenChartTheme
            ? chartTheme.barShadowColor
            : 'transparent',
        },
        emphasis: {
          focus: 'series',
        },
      },
    ];
  }

  // 阈值线（对齐 Grafana）：按 config.thresholdColors 在 Y 轴画水平虚线，
  // 跳过基线 0，只挂在第一条系列上。
  const thresholdLines = (config?.thresholdColors || [])
    .map((th) => ({ value: Number(th.value), color: th.color }))
    .filter((th) => !Number.isNaN(th.value) && th.value !== 0);
  if (thresholdLines.length > 0 && option.series.length > 0) {
    option.series[0].markLine = {
      symbol: 'none',
      silent: true,
      data: thresholdLines.map((th) => ({
        yAxis: th.value,
        lineStyle: {
          color: th.color,
          type: 'dashed',
          width: scaleScreenMetricFloat(1.5, screenRenderContext),
        },
        label: {
          show: true,
          position: 'insideEndTop',
          formatter: String(th.value),
          color: th.color,
          fontSize: scaleScreenMetric(10, screenRenderContext),
        },
      })),
    };
  }

  const legendData = option.series.map((item: { name?: string }) => ({
    name: item.name || t('topology.treeValueTitle'),
  }));

  if (loading) {
    return (
      <div className="h-full flex flex-col items-center justify-center">
        <Spin size="small" />
      </div>
    );
  }

  if (!isDataReady || !chartData || chartData.categories.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </div>
    );
  }

  return (
    <div className="h-full flex flex-row">
      {/* 图表区域 */}
      <div className="flex-1 min-h-0">
        <ReactEcharts
          ref={chartRef}
          option={option}
          notMerge={true}
          style={{ height: '100%', width: '100%' }}
        />
      </div>
      {/* 右侧图例 - 竖排 */}
      {legendData.length > 0 && (
        <ChartLegend
          data={legendData}
          colors={chartColors}
          layout="vertical"
          textColor={chartTheme.axisLabelColor}
          scale={widgetScale}
          onSelectionChange={handleLegendChange}
        />
      )}
    </div>
  );
};

export default BarChart;

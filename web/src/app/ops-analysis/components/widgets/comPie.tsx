import React, { useEffect, useRef, useCallback, useState } from 'react';
import ReactEcharts from 'echarts-for-react';
import { Spin, Empty } from 'antd';
import { randomColorForLegend } from '@/app/ops-analysis/utils/randomColorForChart';
import { ChartDataTransformer } from '@/app/ops-analysis/utils/chartDataTransform';
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
} from './shared/screenMetrics';

interface OsPieProps {
  rawData: any;
  loading?: boolean;
  onReady?: (ready: boolean) => void;
  config?: ValueConfig;
  screenRenderContext?: ScreenRenderContext;
}

const OsPie: React.FC<OsPieProps> = ({
  rawData,
  loading = false,
  onReady,
  config,
  screenRenderContext,
}) => {
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
    return ChartDataTransformer.transformToPieData(rawData);
  };

  const chartData = transformData(rawData);
  const isDataReady = chartData.length > 0;
  const showLegend = chartData.length > 0;

  useEffect(() => {
    if (!loading) {
      if (onReady) {
        onReady(isDataReady);
      }
    }
  }, [isDataReady, loading, onReady]);
  const option: any = {
    color: chartColors,
    animation: true,
    calculable: true,
    title: { show: false },
    tooltip: {
      trigger: 'item',
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
        const percent = params.percent || 0;
        const tooltipPaddingY = scaleScreenMetric(4, screenRenderContext);
        const tooltipPaddingX = scaleScreenMetric(8, screenRenderContext);
        const tooltipGap = scaleScreenMetric(4, screenRenderContext);
        const markerSize = scaleScreenMetric(10, screenRenderContext);
        const markerGap = scaleScreenMetric(6, screenRenderContext);
        return `
          <div style="padding: ${tooltipPaddingY}px ${tooltipPaddingX}px;">
            <div style="margin-bottom: ${tooltipGap}px; font-weight: bold;">${params.seriesName}</div>
            <div style="display: flex; align-items: center;">
              <span style="display: inline-block; width: ${markerSize}px; height: ${markerSize}px; background-color: ${params.color}; border-radius: 50%; margin-right: ${markerGap}px;"></span>
              <span>${params.name}: ${params.value} (${percent.toFixed(1)}%)</span>
            </div>
          </div>
        `;
      },
    },
    legend: {
      show: false,
      selected: legendSelected,
    },
    series: [
      {
        name: '',
        type: 'pie',
        center: ['50%', '50%'],
        radius: ['50%', '78%'],
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
              fontSize: scaleScreenMetric(14, screenRenderContext),
              color: chartTheme.pieTitleColor,
              lineHeight: scaleScreenMetric(20, screenRenderContext),
            },
            value: {
              fontSize: scaleScreenMetric(24, screenRenderContext),
              fontWeight: 'bold',
              color: chartTheme.pieValueColor,
              lineHeight: scaleScreenMetric(32, screenRenderContext),
            },
          },
        },
        labelLine: {
          show: false,
          length: scaleScreenMetric(10, screenRenderContext),
          length2: scaleScreenMetric(15, screenRenderContext),
          smooth: true,
        },
        itemStyle: {
          borderRadius: scaleScreenMetric(2, screenRenderContext),
          borderColor: chartTheme.pieBorderColor,
          borderWidth: scaleScreenMetric(1, screenRenderContext),
          shadowBlur: usesScreenChartTheme
            ? scaleScreenMetric(chartTheme.pieShadowBlur, screenRenderContext)
            : 0,
          shadowColor: usesScreenChartTheme
            ? chartTheme.pieShadowColor
            : 'transparent',
        },
        emphasis: {
          focus: 'none',
          scaleSize: scaleScreenMetric(5, screenRenderContext),
        },
        data: chartData || [],
      },
    ],
  };

  if (loading) {
    return (
      <div className="h-full flex flex-col items-center justify-center">
        <Spin size="small" />
      </div>
    );
  }

  if (!isDataReady || !chartData || chartData.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </div>
    );
  }

  return (
    <div className="h-full flex">
      {/* 图表区域 */}
      <div className="flex-1 min-w-0">
        <ReactEcharts
          ref={chartRef}
          option={option}
          notMerge={true}
          style={{ height: '100%', width: '100%' }}
        />
      </div>

      {/* 图例区域 - 带百分比 */}
      {showLegend && (
        <ChartLegend
          data={chartData.map((item: any) => ({ name: item.name, value: item.value }))}
          colors={chartColors}
          layout="vertical"
          showPercent={true}
          textColor={usesScreenChartTheme ? chartTheme.axisLabelColor : undefined}
          scale={widgetScale}
          onSelectionChange={handleLegendChange}
        />
      )}
    </div>
  );
};

export default OsPie;

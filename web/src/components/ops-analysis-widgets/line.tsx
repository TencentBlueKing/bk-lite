import React, { useCallback, useEffect, useRef, useState } from 'react';
import ReactEcharts from 'echarts-for-react';
import {
  ChartDataTransformer,
  getOpsChartTheme,
  randomColorForLegend,
  resolveOpsChartThemeName,
} from '@/components/ops-analysis-widgets/runtime';
import type { ValueConfig } from '@/components/ops-analysis-widgets';
import ChartLegend from '@/components/chart-legend';
import ChartWithSidebarLegend from '@/components/chart-with-sidebar-legend';
import { renderEChartsTooltipCard } from '@/components/echarts-tooltip-card';
import { useTranslation } from '@/utils/i18n';

interface EChartsInstance {
  dispatchAction: (payload: Record<string, any>) => void;
}

export interface OpsAnalysisLineProps {
  rawData: any;
  loading?: boolean;
  onReady?: (ready: boolean) => void;
  config?: ValueConfig;
}

const LINE_SMOOTHNESS = 0.36;

const withAlpha = (color: string, alpha: number) => {
  const normalized = color.trim();

  if (normalized.startsWith('rgba(')) {
    const parts = normalized
      .slice(5, -1)
      .split(',')
      .map((part) => part.trim());
    return `rgba(${parts[0]}, ${parts[1]}, ${parts[2]}, ${alpha})`;
  }

  if (normalized.startsWith('rgb(')) {
    const parts = normalized
      .slice(4, -1)
      .split(',')
      .map((part) => part.trim());
    return `rgba(${parts[0]}, ${parts[1]}, ${parts[2]}, ${alpha})`;
  }

  return color;
};

const getSeriesAreaColor = (color: string, fillOpacity?: number) => {
  const top =
    typeof fillOpacity === 'number' && fillOpacity >= 0 && fillOpacity <= 1
      ? fillOpacity
      : 0.12;
  return {
    type: 'linear' as const,
    x: 0,
    y: 0,
    x2: 0,
    y2: 1,
    colorStops: [
      { offset: 0, color: withAlpha(color, top) },
      { offset: 0.52, color: withAlpha(color, top * 0.4) },
      { offset: 1, color: withAlpha(color, 0) },
    ],
  };
};

const OpsAnalysisLine: React.FC<OpsAnalysisLineProps> = ({
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
  const [zoomRange, setZoomRange] = useState<{ start: number; end: number }>({
    start: 0,
    end: 100,
  });

  const isZoomed = zoomRange.start !== 0 || zoomRange.end !== 100;

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

  useEffect(() => {
    setZoomRange({ start: 0, end: 100 });
  }, [rawData]);

  const activateDataZoomSelect = useCallback(() => {
    const instance = chartRef.current?.getEchartsInstance() as EChartsInstance | undefined;
    if (instance) {
      instance.dispatchAction({
        type: 'takeGlobalCursor',
        key: 'dataZoomSelect',
        dataZoomSelectActive: true,
      });
    }
  }, []);

  const scheduleActivateDataZoomSelect = useCallback(() => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        activateDataZoomSelect();
      });
    });
  }, [activateDataZoomSelect]);

  useEffect(() => {
    if (!isDataReady) return;
    scheduleActivateDataZoomSelect();
  }, [legendSelected, rawData, zoomRange, isDataReady, scheduleActivateDataZoomSelect]);

  const handleDataZoom = useCallback(() => {
    const instance = chartRef.current?.getEchartsInstance();
    if (!instance) return;
    const optionState = instance.getOption?.();
    const dataZoomState = optionState?.dataZoom;
    if (dataZoomState && Array.isArray(dataZoomState) && dataZoomState.length > 0) {
      const { start, end } = dataZoomState[0] as { start: number; end: number };
      if (start !== undefined && end !== undefined) {
        if (start !== zoomRange.start || end !== zoomRange.end) {
          setZoomRange({ start, end });
        }
      }
    }
  }, [zoomRange]);

  const handleResetZoom = useCallback(() => {
    setZoomRange({ start: 0, end: 100 });
  }, []);

  const handleDblClick = useCallback(() => {
    if (isZoomed) {
      setZoomRange({ start: 0, end: 100 });
    }
  }, [isZoomed]);

  const handleChartReady = useCallback(() => {
    if (!isDataReady) return;
    scheduleActivateDataZoomSelect();
  }, [isDataReady, scheduleActivateDataZoomSelect]);

  const option: any = {
    color: chartColors,
    animation: false,
    calculable: true,
    title: { show: false },
    legend: {
      show: false,
      selected: legendSelected,
    },
    toolbox: {
      show: true,
      feature: {
        dataZoom: {
          show: true,
          yAxisIndex: 'none',
          title: { zoom: '', back: '' },
          icon: { zoom: 'none', back: 'none' },
          brushStyle: {
            borderWidth: 2,
            color: chartTheme.zoomBrushColor,
            borderColor: chartTheme.zoomBrushBorderColor,
          },
        },
      },
      itemSize: 0,
      top: -9999,
    },
    dataZoom: [
      {
        type: 'inside',
        xAxisIndex: 0,
        start: zoomRange.start,
        end: zoomRange.end,
        zoomOnMouseWheel: false,
        moveOnMouseMove: false,
        moveOnMouseWheel: false,
      },
    ],
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'line',
        lineStyle: {
          color: chartTheme.axisPointerColor,
          type: 'dashed',
          width: 1,
        },
      },
      enterable: false,
      confine: true,
      position: function (point: number[], _params: any, _dom: any, _rect: any, size: any) {
        const tooltipWidth = size.contentSize[0];
        const chartWidth = size.viewSize[0];
        let x = point[0] + 40;
        const y = 10;
        if (x + tooltipWidth > chartWidth) {
          x = point[0] - tooltipWidth - 40;
        }
        return [x, y];
      },
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
            markerShape: 'circle',
            label: param.seriesName || '--',
            value: param.value ?? '--',
          })),
        });
      },
    },
    grid: {
      top: 18,
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
          type: 'dashed',
        },
      },
    },
  };

  const DUAL_AXIS_THRESHOLD = 5;
  let useDualAxis = false;
  let largeSeriesIndices: number[] = [];

  if (chartData && chartData.series && chartData.series.length >= 2) {
    const seriesMaxValues = chartData.series.map((item: any) => {
      const numericValues = (item.data || []).filter(
        (value: any) => typeof value === 'number' && value > 0,
      );
      return numericValues.length > 0 ? Math.max(...numericValues) : 0;
    });
    const maxVal = Math.max(...seriesMaxValues);
    const minVal = Math.min(...seriesMaxValues.filter((value: number) => value > 0));
    if (minVal > 0 && maxVal / minVal >= DUAL_AXIS_THRESHOLD) {
      useDualAxis = true;
      const threshold = maxVal / DUAL_AXIS_THRESHOLD;
      largeSeriesIndices = seriesMaxValues
        .map((value: number, index: number) => (value >= threshold ? index : -1))
        .filter((index: number) => index >= 0);
    }
  }

  if (useDualAxis) {
    option.yAxis = [
      {
        type: 'value',
        minInterval: 1,
        axisTick: { show: false },
        axisLine: { show: false },
        axisLabel: {
          formatter: (value: number) =>
            value >= 1000 ? (value / 1000).toFixed(1) + 'k' : value.toString(),
          textStyle: { color: chartTheme.axisLabelColor },
        },
        splitLine: {
          show: true,
          lineStyle: { color: chartTheme.splitLineColor, type: 'dashed' },
        },
      },
      {
        type: 'value',
        minInterval: 1,
        axisTick: { show: false },
        axisLine: { show: false },
        axisLabel: {
          formatter: (value: number) =>
            value >= 1000 ? (value / 1000).toFixed(1) + 'k' : value.toString(),
          textStyle: { color: chartTheme.axisLabelColor },
        },
        splitLine: { show: false },
      },
    ];
    option.grid.right = 40;
  }

  if (chartData && chartData.series) {
    option.series = chartData.series.map((item: any, index: number) => ({
      name: item.name,
      type: 'line',
      data: item.data,
      smooth: LINE_SMOOTHNESS,
      smoothMonotone: 'x',
      symbol: 'none',
      ...(config?.stack ? { stack: 'total' } : {}),
      yAxisIndex: useDualAxis ? (largeSeriesIndices.includes(index) ? 0 : 1) : 0,
      lineStyle: {
        width: chartTheme.lineWidth,
        opacity: chartTheme.lineOpacity,
      },
      itemStyle: {
        borderColor: chartTheme.panelBg,
        borderWidth: 1,
      },
      areaStyle: {
        color: getSeriesAreaColor(
          chartColors[index % chartColors.length],
          config?.fillOpacity,
        ),
      },
      emphasis: {
        focus: 'series',
        lineStyle: {
          width: chartTheme.lineWidth + 0.8,
        },
      },
    }));
  } else {
    option.series = [
      {
        name: t('topology.treeValueTitle'),
        type: 'line',
        data: chartData && chartData.values ? chartData.values : [],
        smooth: LINE_SMOOTHNESS,
        smoothMonotone: 'x',
        symbol: 'none',
        lineStyle: {
          width: chartTheme.lineWidth,
          opacity: chartTheme.lineOpacity,
        },
        itemStyle: {
          borderColor: chartTheme.panelBg,
          borderWidth: 1,
        },
        areaStyle: {
          color: getSeriesAreaColor(chartColors[0], config?.fillOpacity),
        },
        emphasis: {
          focus: 'series',
          lineStyle: {
            width: chartTheme.lineWidth + 0.8,
          },
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
        <div className="relative flex-1 min-w-0">
          {isZoomed && (
            <button
              onClick={handleResetZoom}
              className="absolute top-0 right-1 z-10 cursor-pointer rounded px-1.5 py-0.5 text-[10px] leading-tight shadow-sm transition-colors"
              style={{
                backgroundColor: 'var(--color-bg-2)',
                border: '1px solid var(--color-border-1)',
                color: 'var(--color-text-2)',
              }}
              onMouseEnter={(event) => {
                event.currentTarget.style.backgroundColor = 'var(--color-fill-2)';
                event.currentTarget.style.borderColor = 'var(--color-border-2)';
                event.currentTarget.style.color = 'var(--color-text-1)';
              }}
              onMouseLeave={(event) => {
                event.currentTarget.style.backgroundColor = 'var(--color-bg-2)';
                event.currentTarget.style.borderColor = 'var(--color-border-1)';
                event.currentTarget.style.color = 'var(--color-text-2)';
              }}
            >
              {t('common.reset')}
            </button>
          )}
          <ReactEcharts
            ref={chartRef}
            option={option}
            notMerge={true}
            style={{ height: '100%', width: '100%' }}
            onChartReady={handleChartReady}
            onEvents={{ datazoom: handleDataZoom, dblclick: handleDblClick }}
          />
        </div>
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
      surfaceProps={{
        loading,
        hasData: !!(isDataReady && chartData && chartData.categories.length > 0),
        containerClassName: 'flex h-full w-full',
        loadingClassName: 'flex h-full w-full items-center justify-center',
        emptyClassName: 'flex h-full w-full items-center justify-center',
      }}
    />
  );
};

export default OpsAnalysisLine;

import React, { useEffect, useRef, useCallback, useState } from 'react';
import ReactEcharts from 'echarts-for-react';
import { Spin, Empty } from 'antd';
import { randomColorForLegend } from '@/app/ops-analysis/utils/randomColorForChart';
import { ChartDataTransformer } from '@/app/ops-analysis/utils/chartDataTransform';
import { useTranslation } from '@/utils/i18n';
import {
  getOpsChartTheme,
  resolveOpsChartThemeName,
} from '@/app/ops-analysis/utils/chartTheme';
import ChartLegend from '../components/chartLegend';

interface EChartsInstance {
  dispatchAction: (payload: Record<string, any>) => void;
}

interface TrendLineProps {
  rawData: any;
  loading?: boolean;
  onReady?: (ready: boolean) => void;
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

const getSeriesAreaColor = (color: string) => ({
  type: 'linear' as const,
  x: 0,
  y: 0,
  x2: 0,
  y2: 1,
  colorStops: [
    { offset: 0, color: withAlpha(color, 0.12) },
    { offset: 0.52, color: withAlpha(color, 0.045) },
    { offset: 1, color: withAlpha(color, 0) },
  ],
});

const TrendLine: React.FC<TrendLineProps> = ({
  rawData,
  loading = false,
  onReady,
}) => {
  const { t } = useTranslation();
  const chartRef = useRef<any>(null);
  const themeName = resolveOpsChartThemeName();
  const chartTheme = getOpsChartTheme(themeName);
  const chartColors = randomColorForLegend(themeName);
  const [legendSelected, setLegendSelected] = useState<Record<string, boolean>>({});
  const [zoomRange, setZoomRange] = useState<{ start: number; end: number }>({ start: 0, end: 100 });

  const isZoomed = zoomRange.start !== 0 || zoomRange.end !== 100;

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
    const opt = instance.getOption?.();
    const dz = opt?.dataZoom;
    if (dz && Array.isArray(dz) && dz.length > 0) {
      const { start, end } = dz[0] as { start: number; end: number };
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
        // 默认放右上方，离鼠标远一些
        let x = point[0] + 40;
        const y = 10;
        // 如果右边放不下，放左边
        if (x + tooltipWidth > chartWidth) {
          x = point[0] - tooltipWidth - 40;
        }
        return [x, y];
      },
      backgroundColor: chartTheme.tooltipBackgroundColor,
      borderWidth: 1,
      borderColor: chartTheme.tooltipBorderColor,
      extraCssText: `box-shadow: ${chartTheme.tooltipShadow};`,
      textStyle: {
        fontSize: 12,
        color: chartTheme.tooltipTextColor,
      },
      formatter: function (params: any) {
        if (!params || params.length === 0) return '';
        let content = `<div style="padding: 4px 8px;">
          <div style="margin-bottom: 4px; font-weight: bold;">${params[0].axisValueLabel}</div>`;

        params.forEach((param: any) => {
          content += `
            <div style="display: flex; align-items: center; margin-bottom: 2px;">
              <span style="display: inline-block; width: 10px; height: 10px; background-color: ${param.color}; border-radius: 50%; margin-right: 6px;"></span>
              <span>${param.seriesName}: ${param.value}</span>
            </div>`;
        });

        content += '</div>';
        return content;
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

  // 根据数据类型设置 series
  // 自动双Y轴：当多系列最大值差距超过5倍时启用
  const DUAL_AXIS_THRESHOLD = 5;
  let useDualAxis = false;
  let largeSeriesIndices: number[] = [];

  if (chartData && chartData.series && chartData.series.length >= 2) {
    const seriesMaxValues = chartData.series.map((item: any) => {
      const nums = (item.data || []).filter((v: any) => typeof v === 'number' && v > 0);
      return nums.length > 0 ? Math.max(...nums) : 0;
    });
    const maxVal = Math.max(...seriesMaxValues);
    const minVal = Math.min(...seriesMaxValues.filter((v: number) => v > 0));
    if (minVal > 0 && maxVal / minVal >= DUAL_AXIS_THRESHOLD) {
      useDualAxis = true;
      // 把最大值最大的那些系列放左轴，其余放右轴
      const threshold = maxVal / DUAL_AXIS_THRESHOLD;
      largeSeriesIndices = seriesMaxValues
        .map((v: number, i: number) => (v >= threshold ? i : -1))
        .filter((i: number) => i >= 0);
    }
  }

  if (useDualAxis) {
    // 双Y轴配置
    option.yAxis = [
      {
        type: 'value',
        minInterval: 1,
        axisTick: { show: false },
        axisLine: { show: false },
        axisLabel: {
          formatter: (value: number) => value >= 1000 ? (value / 1000).toFixed(1) + 'k' : value.toString(),
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
          formatter: (value: number) => value >= 1000 ? (value / 1000).toFixed(1) + 'k' : value.toString(),
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
      yAxisIndex: useDualAxis
        ? largeSeriesIndices.includes(index)
          ? 0
          : 1
        : 0,
      lineStyle: {
        width: chartTheme.lineWidth,
        opacity: chartTheme.lineOpacity,
      },
      itemStyle: {
        borderColor: chartTheme.panelBg,
        borderWidth: 1,
      },
      areaStyle: {
        color: getSeriesAreaColor(chartColors[index % chartColors.length]),
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
          color: getSeriesAreaColor(chartColors[0]),
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
    <div className="h-full flex">
      {/* 图表区域 */}
      <div className="flex-1 min-w-0 relative">
        {isZoomed && (
          <button
            onClick={handleResetZoom}
            className="absolute top-0 right-1 z-10 px-1.5 py-0.5 text-[10px] leading-tight rounded shadow-sm transition-colors cursor-pointer"
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

      {/* 右侧图例 */}
      {legendData.length > 0 && (
        <ChartLegend
          data={legendData}
          colors={chartColors}
          layout="vertical"
          onSelectionChange={handleLegendChange}
        />
      )}
    </div>
  );
};

export default TrendLine;

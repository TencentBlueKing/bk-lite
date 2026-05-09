import React, { useEffect, useState, useRef, useCallback } from 'react';
import ReactEcharts from 'echarts-for-react';
import ChartLegend from '../components/chartLegend';
import { Spin, Empty } from 'antd';
import { randomColorForLegend } from '@/app/log/utils/randomColorForChart';
import { ChartDataTransformer } from '@/app/log/utils/chartDataTransform';
import { DashboardBarChartProps } from '@/app/log/types';

const LEGEND_WIDTH_CLASS = 'w-40';
const LEGEND_WIDTH_PX = 160;
const LEGEND_GAP_PX = 8;
const CHART_MIN_WIDTH_PX = 200;

const BarChart: React.FC<DashboardBarChartProps> = ({
  rawData,
  loading = false,
  config,
  onReady
}) => {
  const [isDataReady, setIsDataReady] = useState(false);
  const [showLegend, setShowLegend] = useState(true);
  const chartRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const observerRef = useRef<ResizeObserver | null>(null);
  const chartColors = randomColorForLegend();

  const containerCallbackRef = useCallback((node: HTMLDivElement | null) => {
    if (observerRef.current) {
      observerRef.current.disconnect();
      observerRef.current = null;
    }
    containerRef.current = node;
    if (!node) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const containerWidth = entry.contentRect.width;
        setShowLegend(
          containerWidth >= CHART_MIN_WIDTH_PX + LEGEND_WIDTH_PX + LEGEND_GAP_PX
        );
      }
    });
    observer.observe(node);
    observerRef.current = observer;
  }, []);

  useEffect(() => {
    return () => {
      observerRef.current?.disconnect();
    };
  }, []);

  const transformData = (rawData: any) => {
    const maps = config?.displayMaps;
    if (maps?.key && maps?.value && Array.isArray(rawData)) {
      const mapped = rawData.map((item: any) => ({
        name: item[maps.key],
        count: Number(item[maps.value]) || 0
      }));
      return ChartDataTransformer.transformToLineBarData(mapped);
    }
    return ChartDataTransformer.transformToLineBarData(rawData);
  };

  const chartData = transformData(rawData);
  const isHorizontal = config?.direction === 'horizontal';

  useEffect(() => {
    if (!loading) {
      const hasData = chartData && chartData.categories.length > 0;
      setIsDataReady(hasData);
      if (onReady) {
        onReady(hasData);
      }
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
        type: 'shadow'
      },
      enterable: true,
      confine: false,
      extraCssText: 'box-shadow: 0 0 3px rgba(150,150,150, 0.7);',
      textStyle: {
        fontSize: 12
      },
      formatter: function (params: any) {
        if (!params || params.length === 0) return '';
        let content = `<div style="padding: 4px 8px;">
          <div style="margin-bottom: 4px; font-weight: bold;">${params[0].axisValueLabel}</div>`;

        params.forEach((param: any) => {
          content += `
            <div style="display: flex; align-items: center; margin-bottom: 2px;">
              <span style="display: inline-block; width: 10px; height: 10px; background-color: ${param.color}; border-radius: 2px; margin-right: 6px;"></span>
              <span>${param.seriesName}: ${param.value}</span>
            </div>`;
        });

        content += '</div>';
        return content;
      }
    },
    grid: {
      top: 14,
      left: 18,
      right: 24,
      bottom: 20,
      containLabel: true
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
          textStyle: { color: '#7f92a7' }
        },
        splitLine: {
          show: true,
          lineStyle: { color: '#f0f0f0', type: 'solid' }
        }
      }
      : {
        type: 'category',
        data: chartData?.categories || [],
        nameRotate: -90,
        axisLabel: {
          margin: 15,
          textStyle: {
            color: '#7f92a7',
            fontSize: 11
          },
          rotate: 0,
          interval: 'auto',
          formatter: function (value: string) {
            return value;
          }
        },
        axisLine: {
          lineStyle: {
            color: '#e8e8e8'
          }
        },
        axisTick: {
          show: false
        },
        splitLine: {
          show: false,
          lineStyle: {
            color: '#f0f0f0'
          }
        }
      },
    yAxis: isHorizontal
      ? {
        type: 'category',
        data: chartData?.categories || [],
        axisLabel: {
          textStyle: {
            color: '#7f92a7',
            fontSize: 11
          },
          formatter: function (value: string) {
            return value.length > 12 ? value.slice(0, 12) + '...' : value;
          }
        },
        axisLine: { lineStyle: { color: '#e8e8e8' } },
        axisTick: { show: false },
        inverse: true
      }
      : {
        type: 'value',
        minInterval: 1,
        axisTick: {
          show: false
        },
        axisLine: {
          show: false
        },
        axisLabel: {
          formatter: function (value: number) {
            if (value >= 1000) {
              return (value / 1000).toFixed(1) + 'k';
            }
            return value.toString();
          },
          textStyle: {
            color: '#7f92a7'
          }
        },
        splitLine: {
          show: true,
          lineStyle: {
            color: '#f0f0f0',
            type: 'solid'
          }
        }
      }
  };

  // 根据数据类型设置 series
  const barRadius = isHorizontal ? [0, 2, 2, 0] : [2, 2, 0, 0];
  if (chartData && chartData.series) {
    option.series = chartData.series.map((item: any) => ({
      name: item.name,
      type: 'bar',
      data: item.data,
      barMaxWidth: 40,
      itemStyle: {
        borderRadius: barRadius
      },
      emphasis: {
        focus: 'series'
      }
    }));
  } else {
    option.series = [
      {
        name: '数量',
        type: 'bar',
        data: chartData && chartData.values ? chartData.values : [],
        barMaxWidth: 40,
        itemStyle: {
          borderRadius: barRadius
        },
        emphasis: {
          focus: 'series'
        }
      }
    ];
  }

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
    <div
      className="h-full flex w-full overflow-hidden"
      ref={containerCallbackRef}
    >
      {/* 图表区域 */}
      <div className="flex-1 min-w-[200px]">
        <ReactEcharts
          ref={chartRef}
          option={option}
          style={{ height: '100%', width: '100%' }}
        />
      </div>

      {/* 图例区域 - 仅在多系列数据时显示 */}
      {showLegend && chartData?.series && chartData.series.length > 1 && (
        <div
          className={`ml-2 h-full ${LEGEND_WIDTH_CLASS} flex-shrink-0 min-w-0`}
        >
          <ChartLegend
            chart={chartRef.current?.getEchartsInstance()}
            data={chartData.series}
            colors={chartColors}
          />
        </div>
      )}
    </div>
  );
};

export default BarChart;

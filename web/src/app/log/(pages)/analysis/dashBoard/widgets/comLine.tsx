import React, { useEffect, useState, useRef, useCallback } from 'react';
import ReactEcharts from 'echarts-for-react';
import ChartLegend from '../components/chartLegend';
import { Spin, Empty } from 'antd';
import { randomColorForLegend } from '@/app/log/utils/randomColorForChart';
import { ChartDataTransformer } from '@/app/log/utils/chartDataTransform';
import useChartColors from './docker/useChartColors';

const LEGEND_WIDTH_CLASS = 'w-40';
const LEGEND_WIDTH_PX = 160; // w-40 = 10rem = 160px
const LEGEND_GAP_PX = 8; // ml-2 = 0.5rem = 8px
const CHART_MIN_WIDTH_PX = 200;

interface TrendLineProps {
  rawData: any;
  loading?: boolean;
  config?: any;
  onReady?: (ready: boolean) => void;
}

const TrendLine: React.FC<TrendLineProps> = ({
  rawData,
  loading = false,
  config,
  onReady
}) => {
  const [isDataReady, setIsDataReady] = useState(false);
  const [chartInstance, setChartInstance] = useState<any>(null);
  const [showLegend, setShowLegend] = useState(true);
  const chartRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const observerRef = useRef<ResizeObserver | null>(null);
  const seriesColors = randomColorForLegend();
  const colors = useChartColors();

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
    // 处理嵌套的配置结构
    const chartConfig = config?.displayMaps || config;
    return ChartDataTransformer.transformToLineBarData(rawData, chartConfig);
  };

  const chartData: any = transformData(rawData);

  // 获取tooltip显示的字段名
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
      areaOpacity: isStacked ? 0.18 : 0.1
    };
  };

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
    color: seriesColors,
    animation: false,
    calculable: true,
    title: { show: false },
    legend: {
      show: false
    },
    toolbox: { show: false },
    tooltip: {
      trigger: 'axis',
      appendToBody: true,
      axisPointer: {
        type: 'cross'
      },
      enterable: true,
      confine: false,
      extraCssText: 'box-shadow: 0 0 3px rgba(150,150,150, 0.7);',
      textStyle: {
        fontSize: 12
      },
      formatter: function (params: any) {
        if (!params || params.length === 0) return '';
        const tooltipFieldName = getTooltipFieldName();
        let content = `<div style="padding: 4px 8px;">
          <div style="margin-bottom: 4px; font-weight: bold;">${params[0].axisValueLabel}</div>`;

        params.forEach((param: any) => {
          const displayName = param.seriesName || tooltipFieldName;
          const value =
            param.value !== null && param.value !== undefined
              ? param.value
              : '--';
          content += `
            <div style="display: flex; align-items: center; margin-bottom: 2px;">
              <span style="display: inline-block; width: 10px; height: 10px; background-color: ${param.color}; border-radius: 50%; margin-right: 6px;"></span>
              <span>${displayName}: ${value}</span>
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
    xAxis: {
      type: 'category',
      data: chartData?.categories || [],
      nameRotate: -90,
      axisLabel: {
        margin: 15,
        textStyle: {
          color: colors.axisLabel,
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
          color: colors.axisLine
        }
      },
      axisTick: {
        show: false
      },
      splitLine: {
        show: false,
        lineStyle: {
          color: colors.splitLine
        }
      }
    },
    yAxis: {
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
          color: colors.axisLabel
        }
      },
      splitLine: {
        show: true,
        lineStyle: {
          color: colors.splitLine,
          type: 'solid'
        }
      }
    }
  };

  const { isStacked, lineWidth, areaOpacity } = getSeriesOptions();

  // 根据数据类型设置 series
  if (chartData && chartData.series) {
    option.series = chartData.series.map((item: any, index: number) => ({
      name: item.name,
      type: 'line',
      data: item.data,
      ...(isStacked ? { stack: 'total' } : {}),
      smooth: true,
      symbol: 'none',
      lineStyle: {
        width: lineWidth
      },
      areaStyle: {
        opacity: areaOpacity,
        color: {
          type: 'linear',
          x: 0,
          y: 0,
          x2: 0,
          y2: 1,
          colorStops: [
            {
              offset: 0,
              color: seriesColors[index % seriesColors.length] || colors.primary
            },
            {
              offset: 1,
              color: 'rgba(255, 255, 255, 0)'
            }
          ]
        }
      },
      emphasis: {
        focus: 'series'
      }
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
          width: lineWidth
        },
        areaStyle: {
          opacity: areaOpacity,
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              {
                offset: 0,
                color: seriesColors[0] || colors.primary
              },
              {
                offset: 1,
                color: 'rgba(255, 255, 255, 0)'
              }
            ]
          }
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
          onChartReady={(chart: any) => {
            setChartInstance(chart);
          }}
        />
      </div>

      {showLegend && chartData?.series && chartData.series.length > 1 && (
        <div
          className={`ml-2 h-full ${LEGEND_WIDTH_CLASS} flex-shrink-0 min-w-0`}
        >
          <ChartLegend
            chart={chartInstance}
            data={chartData.series}
            colors={seriesColors}
          />
        </div>
      )}
    </div>
  );
};

export default TrendLine;

import React, { useEffect, useRef, useCallback, useState } from 'react';
import ReactEcharts from 'echarts-for-react';
import ChartLegend from '../components/chartLegend';
import { Spin, Empty } from 'antd';
import { randomColorForLegend } from '@/app/ops-analysis/utils/randomColorForChart';
import { ChartDataTransformer } from '@/app/ops-analysis/utils/chartDataTransform';
import { useTranslation } from '@/utils/i18n';

interface EChartsInstance {
  dispatchAction: (payload: Record<string, any>) => void;
}

interface TrendLineProps {
  rawData: any;
  loading?: boolean;
  onReady?: (ready: boolean) => void;
}

const TrendLine: React.FC<TrendLineProps> = ({
  rawData,
  loading = false,
  onReady,
}) => {
  const { t } = useTranslation();
  const chartRef = useRef<any>(null);
  const chartColors = randomColorForLegend();
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
            color: 'rgba(24, 144, 255, 0.25)',
            borderColor: 'rgba(24, 144, 255, 0.8)',
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
        type: 'cross',
      },
      enterable: true,
      confine: true,
      extraCssText: 'box-shadow: 0 0 3px rgba(150,150,150, 0.7);',
      textStyle: {
        fontSize: 12,
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
      top: 14,
      left: 24,
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
          color: '#7f92a7',
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
          color: '#e8e8e8',
        },
      },
      axisTick: {
        show: false,
      },
      splitLine: {
        show: false,
        lineStyle: {
          color: '#f0f0f0',
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
          color: '#7f92a7',
        },
      },
      splitLine: {
        show: true,
        lineStyle: {
          color: '#f0f0f0',
          type: 'solid',
        },
      },
    },
  };

  // 根据数据类型设置 series
  if (chartData && chartData.series) {
    option.series = chartData.series.map((item: any) => ({
      name: item.name,
      type: 'line',
      data: item.data,
      smooth: true,
      symbol: 'none',
      lineStyle: {
        width: 1,
      },
      emphasis: {
        focus: 'series',
      },
    }));
  } else {
    option.series = [
      {
        name: t('topology.treeValueTitle'),
        type: 'line',
        data: chartData && chartData.values ? chartData.values : [],
        smooth: true,
        symbol: 'none',
        lineStyle: {
          width: 1,
        },
        emphasis: {
          focus: 'series',
        },
      },
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
    <div className="h-full flex">
      {/* 图表区域 */}
      <div className="flex-1 relative">
        {isZoomed && (
          <button
            onClick={handleResetZoom}
            className="absolute top-0 right-1 z-10 px-1.5 py-0.5 text-[10px] leading-tight bg-white border border-gray-300 rounded shadow-sm text-gray-600 hover:bg-gray-50 hover:text-blue-600 hover:border-blue-300 transition-colors cursor-pointer"
          >
            恢复
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

      {chartData?.series && chartData.series.length > 1 && (
        <div className="w-38 ml-2 shrink-0 h-full">
          <ChartLegend
            data={chartData.series}
            colors={chartColors}
            onSelectionChange={handleLegendChange}
          />
        </div>
      )}
    </div>
  );
};

export default TrendLine;

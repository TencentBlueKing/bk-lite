import React, { useEffect, useState, useRef, useCallback } from 'react';
import ReactEcharts from 'echarts-for-react';
import { Spin, Empty } from 'antd';
import { randomColorForLegend } from '@/app/log/utils/randomColorForChart';
import { ChartDataTransformer } from '@/app/log/utils/chartDataTransform';
import ChartLegend from '../components/chartLegend';
import useChartColors from './docker/useChartColors';

const LEGEND_WIDTH_CLASS = 'w-40';
const LEGEND_WIDTH_PX = 160;
const LEGEND_GAP_PX = 8;
const CHART_MIN_WIDTH_PX = 200;

interface ComBarLineProps {
  rawData: any;
  loading?: boolean;
  config?: any;
  onReady?: (ready: boolean) => void;
}

const ComBarLine: React.FC<ComBarLineProps> = ({
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
  const chartColors = randomColorForLegend();
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

  const chartConfig = config?.displayMaps || config;
  const chartData = ChartDataTransformer.transformToLineBarData(rawData, chartConfig);

  useEffect(() => {
    if (!loading) {
      const hasData = chartData && chartData.categories.length > 0;
      setIsDataReady(hasData);
      if (onReady) onReady(hasData);
    }
  }, [chartData, loading, onReady]);

  const barLabel = chartConfig?.barLabel || '数量';
  const lineLabel = chartConfig?.lineLabel || '趋势';

  const option: any = {
    color: chartColors,
    animation: false,
    title: { show: false },
    legend: { show: false },
    toolbox: { show: false },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      appendToBody: true,
      confine: false,
      textStyle: { fontSize: 12 }
    },
    grid: {
      top: 10,
      left: 18,
      right: 18,
      bottom: 20,
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: chartData?.categories || [],
      axisLabel: {
        textStyle: { color: colors.axisLabel, fontSize: 11 },
        interval: 'auto'
      },
      axisLine: { lineStyle: { color: colors.axisLine } },
      axisTick: { show: false }
    },
    yAxis: [
      {
        type: 'value',
        minInterval: 1,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          formatter: (v: number) => (v >= 1000 ? (v / 1000).toFixed(1) + 'k' : v.toString()),
          textStyle: { color: colors.axisLabel }
        },
        splitLine: {
          lineStyle: { color: colors.splitLine, type: 'solid' }
        }
      },
      {
        type: 'value',
        minInterval: 1,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          formatter: (v: number) => (v >= 1000 ? (v / 1000).toFixed(1) + 'k' : v.toString()),
          textStyle: { color: colors.axisLabel }
        },
        splitLine: { show: false }
      }
    ],
    series: []
  };

  if (chartData?.series && chartData.series.length >= 2) {
    option.series = [
      {
        name: chartData.series[0].name || barLabel,
        type: 'bar',
        data: chartData.series[0].data,
        yAxisIndex: 0,
        barMaxWidth: 40,
        itemStyle: {
          borderRadius: [2, 2, 0, 0],
          color: chartColors[0]
        }
      },
      {
        name: chartData.series[1].name || lineLabel,
        type: 'line',
        data: chartData.series[1].data,
        yAxisIndex: 1,
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 2, color: chartColors[1] }
      }
    ];
  } else if (chartData?.values) {
    option.series = [
      {
        name: barLabel,
        type: 'bar',
        data: chartData.values,
        barMaxWidth: 40,
        itemStyle: { borderRadius: [2, 2, 0, 0] }
      }
    ];
  }

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Spin size="small" />
      </div>
    );
  }

  if (!isDataReady || !chartData || chartData.categories.length === 0) {
    return (
      <div className="h-full flex items-center justify-center">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </div>
    );
  }

  const seriesData = chartData?.series && chartData.series.length > 1 ? chartData.series : null;

  return (
    <div className="h-full flex w-full overflow-hidden" ref={containerCallbackRef}>
      <div className="flex-1 min-w-[200px]">
        <ReactEcharts
          ref={chartRef}
          option={option}
          style={{ height: '100%', width: '100%' }}
          onChartReady={(chart: any) => setChartInstance(chart)}
        />
      </div>
      {showLegend && seriesData && (
        <div className={`ml-2 h-full ${LEGEND_WIDTH_CLASS} flex-shrink-0 min-w-0`}>
          <ChartLegend
            chart={chartInstance}
            data={seriesData}
            colors={chartColors}
          />
        </div>
      )}
    </div>
  );
};

export default ComBarLine;

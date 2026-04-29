import React, { useEffect, useState, useCallback, useRef } from 'react';
import ReactEcharts from 'echarts-for-react';
import ChartLegend from '../components/chartLegend';
import { Spin, Empty } from 'antd';
import { randomColorForLegend } from '@/app/log/utils/randomColorForChart';
import { ChartDataTransformer } from '@/app/log/utils/chartDataTransform';

interface OsPieProps {
  rawData: any;
  loading?: boolean;
  config?: any;
  onReady?: (ready: boolean) => void;
}

const OsPie: React.FC<OsPieProps> = ({
  rawData,
  loading = false,
  config,
  onReady
}) => {
  const [isDataReady, setIsDataReady] = useState(false);
  const [chartInstance, setChartInstance] = useState<any>(null);
  const [showLegend, setShowLegend] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);
  const chartColors = randomColorForLegend();

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setShowLegend(entry.contentRect.width >= 360);
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const onChartReady = useCallback((instance: any) => {
    setChartInstance(instance);
  }, []);

  const transformData = (rawData: any) => {
    // 如果有 displayMaps 配置，先将原始数据映射为 {name, value} 格式
    const displayMaps = config?.displayMaps;
    if (displayMaps?.key && displayMaps?.value && Array.isArray(rawData)) {
      const mapped = rawData
        .filter((item: any) => item[displayMaps.key] !== undefined)
        .map((item: any) => ({
          name: String(item[displayMaps.key]),
          value: parseFloat(item[displayMaps.value]) || 0
        }));
      if (mapped.length > 0) {
        return mapped;
      }
    }
    return ChartDataTransformer.transformToPieData(rawData);
  };

  const chartData = transformData(rawData);
  const useBarChart = chartData && chartData.length > 5;

  useEffect(() => {
    if (!loading) {
      const hasData = chartData && chartData.length > 0;
      setIsDataReady(hasData);
      if (onReady) {
        onReady(hasData);
      }
    }
  }, [chartData, loading, onReady]);

  // Sort data descending for bar chart display
  const sortedBarData = useBarChart
    ? [...chartData].sort((a: any, b: any) => a.value - b.value)
    : [];

  const barOption: any = useBarChart
    ? {
      color: chartColors,
      animation: true,
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        confine: true,
        textStyle: { fontSize: 12 }
      },
      grid: {
        left: 12,
        right: 48,
        top: 8,
        bottom: 8,
        containLabel: true
      },
      xAxis: {
        type: 'value',
        axisLabel: { fontSize: 11, color: '#999' },
        splitLine: { lineStyle: { type: 'dashed', color: '#f0f0f0' } }
      },
      yAxis: {
        type: 'category',
        data: sortedBarData.map((d: any) => d.name),
        axisLabel: {
          fontSize: 11,
          color: '#666',
          width: 100,
          overflow: 'truncate',
          ellipsis: '...'
        },
        axisTick: { show: false },
        axisLine: { show: false }
      },
      series: [
        {
          type: 'bar',
          data: sortedBarData.map((d: any, i: number) => ({
            value: d.value,
            itemStyle: {
              color: chartColors[i % chartColors.length],
              borderRadius: [0, 2, 2, 0]
            }
          })),
          barMaxWidth: 20,
          label: {
            show: true,
            position: 'right',
            fontSize: 11,
            color: '#666'
          }
        }
      ]
    }
    : null;

  const pieOption: any = {
    color: chartColors,
    animation: true,
    calculable: true,
    title: { show: false },
    tooltip: {
      trigger: 'item',
      enterable: true,
      confine: true,
      extraCssText: 'box-shadow: 0 0 3px rgba(150,150,150, 0.7);',
      textStyle: {
        fontSize: 12
      },
      formatter: function (params: any) {
        const percent = params.percent || 0;
        return `
          <div style="padding: 4px 8px;">
            <div style="margin-bottom: 4px; font-weight: bold;">${
              params.seriesName
            }</div>
            <div style="display: flex; align-items: center;">
              <span style="display: inline-block; width: 10px; height: 10px; background-color: ${
                params.color
              }; border-radius: 50%; margin-right: 6px;"></span>
              <span>${params.name}: ${params.value} (${percent.toFixed(
                1
              )}%)</span>
            </div>
          </div>
        `;
      }
    },
    legend: {
      show: false
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
              0
            );
            return `{title|总数}\n{value|${total}}`;
          },
          rich: {
            title: {
              fontSize: 14,
              color: '#666',
              lineHeight: 20
            },
            value: {
              fontSize: 24,
              fontWeight: 'bold',
              color: '#333',
              lineHeight: 32
            }
          }
        },
        labelLine: {
          show: false,
          length: 10,
          length2: 15,
          smooth: true
        },
        itemStyle: {
          borderRadius: 2,
          borderColor: '#fff',
          borderWidth: 1
        },
        emphasis: {
          focus: 'none',
          scaleSize: 5
        },
        data: chartData || []
      }
    ]
  };

  const option = useBarChart ? barOption : pieOption;

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
    <div className="h-full flex" ref={containerRef}>
      {/* 图表区域 */}
      <div className={useBarChart ? 'w-full' : 'flex-1 min-w-[200px]'}>
        <ReactEcharts
          option={option}
          style={{ height: '100%', width: '100%' }}
          onChartReady={onChartReady}
        />
      </div>

      {/* 图例区域 - only for pie/donut */}
      {!useBarChart && showLegend && chartData && chartData.length > 1 && (
        <div className="w-40 flex-shrink-0 h-full">
          <ChartLegend
            chart={chartInstance}
            data={chartData.map((item: any) => ({ name: item.name }))}
            colors={chartColors}
          />
        </div>
      )}
    </div>
  );
};

export default OsPie;

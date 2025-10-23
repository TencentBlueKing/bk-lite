import React, { useEffect, useState, useRef } from 'react';
import ReactEcharts from 'echarts-for-react';
import ChartLegend from '../components/chartLegend';
import { Spin, Empty } from 'antd';
import { randomColorForLegend } from '@/app/ops-analysis/utils/randomColorForChart';
import { ChartDataTransformer } from '@/app/ops-analysis/utils/chartDataTransform';

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
  const [isDataReady, setIsDataReady] = useState(false);
  const chartRef = useRef<any>(null);
  const chartColors = randomColorForLegend();

  const transformData = (rawData: any) => {
    return ChartDataTransformer.transformToLineBarData(rawData);
  };

  const chartData = transformData(rawData);

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
    legend: {
      show: false,
    },
    toolbox: { show: false },
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
      left: 18,
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
        name: '告警数',
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
      <div className="flex-1">
        <ReactEcharts
          ref={chartRef}
          option={option}
          style={{ height: '100%', width: '100%' }}
        />
      </div>

      {chartData?.series && chartData.series.length > 1 && (
        <div className="w-32 ml-2 flex-shrink-0 h-full">
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

export default TrendLine;

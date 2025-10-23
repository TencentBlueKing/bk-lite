import React, { useEffect, useState, useRef } from 'react';
import ReactEcharts from 'echarts-for-react';
import ChartLegend from '../components/chartLegend';
import { Spin, Empty } from 'antd';
import { randomColorForLegend } from '@/app/ops-analysis/utils/randomColorForChart';
import { ChartDataTransformer } from '@/app/ops-analysis/utils/chartDataTransform';

interface OsPieProps {
  rawData: any;
  loading?: boolean;
  onReady?: (ready: boolean) => void;
}

const OsPie: React.FC<OsPieProps> = ({ rawData, loading = false, onReady }) => {
  const [isDataReady, setIsDataReady] = useState(false);
  const chartRef = useRef<any>(null);
  const chartColors = randomColorForLegend();

  const transformData = (rawData: any) => {
    return ChartDataTransformer.transformToPieData(rawData);
  };

  const chartData = transformData(rawData);

  useEffect(() => {
    if (!loading) {
      const hasData = chartData && chartData.length > 0;
      setIsDataReady(hasData);
      if (onReady) {
        onReady(hasData);
      }
    }
  }, [chartData, loading, onReady]);
  const option: any = {
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
        fontSize: 12,
      },
      formatter: function (params: any) {
        const percent = params.percent || 0;
        return `
          <div style="padding: 4px 8px;">
            <div style="margin-bottom: 4px; font-weight: bold;">${params.seriesName}</div>
            <div style="display: flex; align-items: center;">
              <span style="display: inline-block; width: 10px; height: 10px; background-color: ${params.color}; border-radius: 50%; margin-right: 6px;"></span>
              <span>${params.name}: ${params.value} (${percent.toFixed(1)}%)</span>
            </div>
          </div>
        `;
      },
    },
    legend: {
      show: false,
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
              lineHeight: 20,
            },
            value: {
              fontSize: 24,
              fontWeight: 'bold',
              color: '#333',
              lineHeight: 32,
            },
          },
        },
        labelLine: {
          show: false,
          length: 10,
          length2: 15,
          smooth: true,
        },
        itemStyle: {
          borderRadius: 2,
          borderColor: '#fff',
          borderWidth: 1,
        },
        emphasis: {
          focus: 'none',
          scaleSize: 5,
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
      <div className="flex-1">
        <ReactEcharts
          ref={chartRef}
          option={option}
          style={{ height: '100%', width: '100%' }}
        />
      </div>

      {/* 图例区域 */}
      {chartData && chartData.length > 1 && (
        <div className="w-34 flex-shrink-0 h-full">
          <ChartLegend
            chart={chartRef.current?.getEchartsInstance()}
            data={chartData.map((item: any) => ({ name: item.name }))}
            colors={chartColors}
          />
        </div>
      )}
    </div>
  );
};

export default OsPie;

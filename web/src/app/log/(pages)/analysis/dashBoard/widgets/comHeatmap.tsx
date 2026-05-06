import React, { useEffect, useMemo, useState } from 'react';
import ReactEcharts from 'echarts-for-react';
import { Empty, Spin } from 'antd';
import { ChartDataTransformer } from '@/app/log/utils/chartDataTransform';

interface ComHeatmapProps {
  rawData: any;
  loading?: boolean;
  config?: any;
  onReady?: (ready: boolean) => void;
}

const ComHeatmap: React.FC<ComHeatmapProps> = ({
  rawData,
  loading = false,
  config,
  onReady
}) => {
  const [isDataReady, setIsDataReady] = useState(false);

  const heatmapData = useMemo(() => {
    if (!Array.isArray(rawData) || !rawData.length) {
      return {
        xAxis: [],
        yAxis: [],
        values: [],
        max: 0
      };
    }

    const timeKey = config?.displayMaps?.time || '_time';
    const categoryKey = config?.displayMaps?.category || 'container_name';
    const valueKey = config?.displayMaps?.value || 'errcount';

    const rows = rawData
      .filter((item) => item?.[timeKey] && item?.[categoryKey])
      .sort(
        (a, b) =>
          new Date(a[timeKey]).getTime() - new Date(b[timeKey]).getTime()
      );

    const xAxis = [
      ...new Set(
        rows.map((item) => ChartDataTransformer.formatTimeValue(item[timeKey]))
      )
    ];
    const categories = new Map<string, number>();

    rows.forEach((item) => {
      const category = String(item[categoryKey]);
      const current = categories.get(category) || 0;
      categories.set(category, current + (Number(item[valueKey]) || 0));
    });

    const yAxis = [...categories.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, config?.limit || 8)
      .map(([name]) => name);

    const values = rows
      .filter((item) => yAxis.includes(String(item[categoryKey])))
      .map((item) => [
        xAxis.indexOf(ChartDataTransformer.formatTimeValue(item[timeKey])),
        yAxis.indexOf(String(item[categoryKey])),
        Number(item[valueKey]) || 0
      ]);

    return {
      xAxis,
      yAxis,
      values,
      max: Math.max(...values.map((item) => item[2]), 0)
    };
  }, [config, rawData]);

  useEffect(() => {
    if (!loading) {
      const hasData = !!heatmapData.values.length;
      setIsDataReady(hasData);
      onReady?.(hasData);
    }
  }, [heatmapData, loading, onReady]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spin size="small" />
      </div>
    );
  }

  if (!isDataReady) {
    return (
      <div className="flex h-full items-center justify-center">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </div>
    );
  }

  const option = {
    tooltip: {
      confine: true,
      appendToBody: true,
      position: 'top'
    },
    grid: {
      top: 12,
      left: 64,
      right: 12,
      bottom: 56,
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: heatmapData.xAxis,
      splitArea: { show: false },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: '#e8e8e8' } },
      axisLabel: {
        fontSize: 11,
        color: '#7f92a7'
      }
    },
    yAxis: {
      type: 'category',
      data: heatmapData.yAxis,
      splitArea: { show: false },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: '#e8e8e8' } },
      axisLabel: {
        fontSize: 11,
        color: '#7f92a7'
      }
    },
    visualMap: {
      show: true,
      min: 0,
      max: heatmapData.max || 1,
      calculable: false,
      orient: 'horizontal',
      left: 'center',
      bottom: 2,
      inRange: {
        color: ['#F0F6FF', '#CCDEFF', '#8DB8FF', '#5A8FFF']
      }
    },
    series: [
      {
        type: 'heatmap',
        data: heatmapData.values,
        label: {
          show: false
        },
        emphasis: {
          itemStyle: {
            borderColor: '#fff',
            borderWidth: 1
          }
        }
      }
    ]
  };

  return (
    <ReactEcharts option={option} style={{ height: '100%', width: '100%' }} />
  );
};

export default ComHeatmap;

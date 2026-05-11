import React, { useEffect, useState } from 'react';
import ReactEcharts from 'echarts-for-react';
import { Spin, Empty } from 'antd';
import useChartColors from './docker/useChartColors';

interface ComScatterProps {
  rawData: any;
  loading?: boolean;
  config?: any;
  onReady?: (ready: boolean) => void;
}

const COLORS = {
  above: '#e45454',   // 对角线上方（Y > X）：红色
  below: '#3b82f6'    // 对角线下方（Y <= X）：蓝色
};

const ComScatter: React.FC<ComScatterProps> = ({
  rawData,
  loading = false,
  config,
  onReady
}) => {
  const [isDataReady, setIsDataReady] = useState(false);
  const colors = useChartColors();

  const chartConfig = config?.displayMaps || config;
  const xField = chartConfig?.xField || chartConfig?.key || 'x';
  const yField = chartConfig?.yField || chartConfig?.value || 'y';
  const labelField = chartConfig?.labelField || chartConfig?.tooltipField || '';
  const xLabel = chartConfig?.xLabel || xField;
  const yLabel = chartConfig?.yLabel || yField;

  // 解析数据并按对角线分组
  const aboveData: any[] = [];
  const belowData: any[] = [];
  let maxVal = 0;

  if (Array.isArray(rawData) && rawData.length > 0) {
    rawData.forEach((item: any) => {
      const x = parseFloat(item[xField]);
      const y = parseFloat(item[yField]);
      if (isNaN(x) || isNaN(y)) return;
      const label = labelField ? item[labelField] : '';
      const point = [x, y, label];
      if (x > maxVal) maxVal = x;
      if (y > maxVal) maxVal = y;
      if (y > x) {
        aboveData.push(point);
      } else {
        belowData.push(point);
      }
    });
  }

  useEffect(() => {
    if (!loading) {
      const hasData = aboveData.length + belowData.length > 0;
      setIsDataReady(hasData);
      if (onReady) onReady(hasData);
    }
  }, [rawData, loading, onReady]);

  const tooltipFormatter = (params: any) => {
    const d = params.data;
    let content = '<div style="padding: 4px 8px;">';
    if (d[2]) content += `<div style="font-weight:bold; margin-bottom:4px;">${d[2]}</div>`;
    content += `<div>${xLabel}: ${d[0]}</div>`;
    content += `<div>${yLabel}: ${d[1]}</div>`;
    content += '</div>';
    return content;
  };

  const diagonalMax = maxVal * 1.1 || 1;

  const option: any = {
    animation: false,
    title: { show: false },
    legend: { show: false },
    toolbox: { show: false },
    tooltip: {
      trigger: 'item',
      confine: true,
      textStyle: { fontSize: 12 },
      formatter: tooltipFormatter
    },
    grid: {
      top: 14,
      left: 18,
      right: 24,
      bottom: 20,
      containLabel: true
    },
    xAxis: {
      type: 'value',
      axisLine: { lineStyle: { color: colors.axisLine } },
      axisTick: { show: false },
      axisLabel: {
        formatter: (v: number) => (v >= 1000 ? (v / 1000).toFixed(1) + 'k' : v.toString()),
        textStyle: { color: colors.axisLabel }
      },
      splitLine: { show: false }
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        formatter: (v: number) => (v >= 1000 ? (v / 1000).toFixed(1) + 'k' : v.toString()),
        textStyle: { color: colors.axisLabel }
      },
      splitLine: { show: false }
    },
    series: [
      {
        name: yLabel,
        type: 'scatter',
        data: aboveData,
        symbolSize: 8,
        itemStyle: { color: COLORS.above, opacity: 0.75 },
        emphasis: { itemStyle: { opacity: 1 } }
      },
      {
        name: xLabel,
        type: 'scatter',
        data: belowData,
        symbolSize: 8,
        itemStyle: { color: COLORS.below, opacity: 0.75 },
        emphasis: { itemStyle: { opacity: 1 } }
      },
      {
        type: 'line',
        data: [[0, 0], [diagonalMax, diagonalMax]],
        symbol: 'none',
        lineStyle: {
          color: colors.textTertiary,
          type: 'dashed',
          width: 1
        },
        tooltip: { show: false },
        silent: true
      }
    ]
  };

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Spin size="small" />
      </div>
    );
  }

  if (!isDataReady) {
    return (
      <div className="h-full flex items-center justify-center">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </div>
    );
  }

  return (
    <div className="h-full w-full">
      <ReactEcharts
        option={option}
        style={{ height: '100%', width: '100%' }}
      />
    </div>
  );
};

export default ComScatter;

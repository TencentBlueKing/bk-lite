import React, { useEffect, useState } from 'react';
import ReactEcharts from 'echarts-for-react';
import ChartSurface from '@/components/chart-surface';
import useChartColors from '@/hooks/useChartColors';

export interface LogAnalysisScatterProps {
  rawData: any;
  loading?: boolean;
  config?: any;
  onReady?: (ready: boolean) => void;
}

const LogAnalysisScatter: React.FC<LogAnalysisScatterProps> = ({
  rawData,
  loading = false,
  config,
  onReady,
}) => {
  const [isDataReady, setIsDataReady] = useState(false);
  const colors = useChartColors();

  const chartConfig = config?.displayMaps || config;
  const xField = chartConfig?.xField || chartConfig?.key || 'x';
  const yField = chartConfig?.yField || chartConfig?.value || 'y';
  const labelField = chartConfig?.labelField || chartConfig?.tooltipField || '';
  const xLabel = chartConfig?.xLabel || xField;
  const yLabel = chartConfig?.yLabel || yField;

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
      onReady?.(hasData);
    }
  }, [rawData, loading, onReady]);

  const tooltipFormatter = (params: any) => {
    const data = params.data;
    let content = '<div style="padding: 4px 8px;">';
    if (data[2]) {
      content += `<div style="font-weight:bold; margin-bottom:4px;">${data[2]}</div>`;
    }
    content += `<div>${xLabel}: ${data[0]}</div>`;
    content += `<div>${yLabel}: ${data[1]}</div>`;
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
      backgroundColor: colors.tooltipBg,
      borderColor: colors.tooltipBorder,
      textStyle: {
        fontSize: 12,
        color: colors.textPrimary,
      },
      formatter: tooltipFormatter,
    },
    grid: {
      top: 14,
      left: 18,
      right: 24,
      bottom: 20,
      containLabel: true,
    },
    xAxis: {
      type: 'value',
      axisLine: { lineStyle: { color: colors.axisLine } },
      axisTick: { show: false },
      axisLabel: {
        formatter: (value: number) =>
          value >= 1000 ? (value / 1000).toFixed(1) + 'k' : value.toString(),
        textStyle: { color: colors.axisLabel },
      },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        formatter: (value: number) =>
          value >= 1000 ? (value / 1000).toFixed(1) + 'k' : value.toString(),
        textStyle: { color: colors.axisLabel },
      },
      splitLine: { show: false },
    },
    series: [
      {
        name: yLabel,
        type: 'scatter',
        data: aboveData,
        symbolSize: 8,
        itemStyle: { color: colors.danger, opacity: 0.75 },
        emphasis: { itemStyle: { opacity: 1 } },
      },
      {
        name: xLabel,
        type: 'scatter',
        data: belowData,
        symbolSize: 8,
        itemStyle: { color: colors.primary, opacity: 0.75 },
        emphasis: { itemStyle: { opacity: 1 } },
      },
      {
        type: 'line',
        data: [[0, 0], [diagonalMax, diagonalMax]],
        symbol: 'none',
        lineStyle: {
          color: colors.textTertiary,
          type: 'dashed',
          width: 1,
        },
        tooltip: { show: false },
        silent: true,
      },
    ],
  };

  return (
    <ChartSurface
      loading={loading}
      hasData={isDataReady}
      containerClassName="h-full w-full"
      loadingClassName="flex h-full w-full items-center justify-center"
      emptyClassName="flex h-full w-full items-center justify-center"
    >
      <ReactEcharts option={option} style={{ height: '100%', width: '100%' }} />
    </ChartSurface>
  );
};

export default LogAnalysisScatter;

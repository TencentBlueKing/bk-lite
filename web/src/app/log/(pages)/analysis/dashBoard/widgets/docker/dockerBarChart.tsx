import React, { useMemo } from 'react';
import ReactEcharts from 'echarts-for-react';
import { Empty } from 'antd';
import useChartColors from './useChartColors';

interface DockerBarChartProps {
  rawData: any;
  loading?: boolean;
  config?: any;
}

const DockerBarChart: React.FC<DockerBarChartProps> = ({
  rawData,
  loading = false,
  config
}) => {
  const colors = useChartColors();

  const chartOption = useMemo(() => {
    if (!rawData || !Array.isArray(rawData) || rawData.length === 0) return null;

    const displayMaps = config?.displayMaps || {};
    const nameField = displayMaps.key || 'name';
    const valueField = displayMaps.value || 'count';

    const items = rawData
      .map((item: any) => ({
        name: item[nameField] || '',
        value: parseFloat(item[valueField]) || 0
      }))
      .sort((a: any, b: any) => a.value - b.value);

    const categories = items.map((d: any) => d.name);
    const values = items.map((d: any) => d.value);
    const barColor = config?.barColor || colors.primary;

    return {
      tooltip: {
        trigger: 'axis',
        appendToBody: true,
        confine: false,
        axisPointer: { type: 'shadow' },
        backgroundColor: colors.tooltipBg,
        borderColor: colors.tooltipBorder,
        textStyle: { color: colors.textPrimary, fontSize: 12 }
      },
      grid: {
        top: 8,
        right: 60,
        bottom: 8,
        left: 8,
        containLabel: true
      },
      xAxis: {
        type: 'value',
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: colors.splitLine } },
        axisLabel: { color: colors.axisLabel, fontSize: 10 }
      },
      yAxis: {
        type: 'category',
        data: categories,
        axisLine: { lineStyle: { color: colors.axisLine } },
        axisTick: { show: false },
        axisLabel: {
          color: colors.axisLabel,
          fontSize: 10,
          width: 100,
          overflow: 'truncate'
        }
      },
      series: [
        {
          type: 'bar',
          data: values,
          barMaxWidth: 16,
          itemStyle: {
            borderRadius: [0, 3, 3, 0],
            color: {
              type: 'linear',
              x: 0, y: 0, x2: 1, y2: 0,
              colorStops: [
                { offset: 0, color: barColor + '60' },
                { offset: 1, color: barColor }
              ]
            }
          },
          emphasis: {
            itemStyle: {
              color: {
                type: 'linear',
                x: 0, y: 0, x2: 1, y2: 0,
                colorStops: [
                  { offset: 0, color: barColor + '80' },
                  { offset: 1, color: barColor }
                ]
              }
            }
          },
          label: {
            show: true,
            position: 'right',
            color: colors.textSecondary,
            fontSize: 10
          }
        }
      ]
    };
  }, [rawData, config, colors]);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div
          className="w-5 h-5 rounded-full border-2 border-t-transparent animate-spin"
          style={{ borderColor: `${colors.primary}33`, borderTopColor: 'transparent' }}
        />
      </div>
    );
  }

  if (!chartOption) {
    return (
      <div className="h-full flex items-center justify-center">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </div>
    );
  }

  return (
    <ReactEcharts
      option={chartOption}
      style={{ height: '100%', width: '100%' }}
      opts={{ renderer: 'canvas' }}
      notMerge
    />
  );
};

export default DockerBarChart;

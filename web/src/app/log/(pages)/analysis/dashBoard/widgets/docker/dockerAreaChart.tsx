import React, { useMemo } from 'react';
import ReactEcharts from 'echarts-for-react';
import { Empty } from 'antd';
import useChartColors from './useChartColors';

interface DockerAreaChartProps {
  rawData: any;
  loading?: boolean;
  config?: any;
}

const DockerAreaChart: React.FC<DockerAreaChartProps> = ({
  rawData,
  loading = false,
  config
}) => {
  const colors = useChartColors();

  const chartOption = useMemo(() => {
    if (!rawData || !Array.isArray(rawData) || rawData.length === 0) return null;

    const displayMaps = config?.displayMaps || {};
    const field1 = displayMaps.barField || displayMaps.key || 'logcount';
    const field2 = displayMaps.lineField || '';
    const label1 = displayMaps.barLabel || field1;
    const label2 = displayMaps.lineLabel || field2;

    const timeData = rawData.map((item: any) => {
      const t = item._time || item.time || '';
      if (!t) return '';
      const d = new Date(t);
      return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
    });

    const series1Data = rawData.map((item: any) => {
      const v = parseFloat(item[field1]);
      return isNaN(v) ? 0 : v;
    });

    const color1 = colors.series[0];
    const color2 = colors.series[4];

    const seriesList: any[] = [
      {
        name: label1,
        type: 'line',
        stack: 'total',
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 1.5, color: color1 },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: color1 + '40' },
              { offset: 1, color: color1 + '05' }
            ]
          }
        },
        data: series1Data
      }
    ];

    if (field2) {
      const series2Data = rawData.map((item: any) => {
        const v = parseFloat(item[field2]);
        return isNaN(v) ? 0 : v;
      });
      seriesList.push({
        name: label2,
        type: 'line',
        stack: 'total',
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 1.5, color: color2 },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: color2 + '40' },
              { offset: 1, color: color2 + '05' }
            ]
          }
        },
        data: series2Data
      });
    }

    return {
      tooltip: {
        trigger: 'axis',
        appendToBody: true,
        confine: false,
        backgroundColor: colors.tooltipBg,
        borderColor: colors.tooltipBorder,
        textStyle: { color: colors.textPrimary, fontSize: 12 }
      },
      legend: {
        bottom: 4,
        textStyle: { color: colors.textSecondary, fontSize: 11 },
        itemWidth: 12,
        itemHeight: 8
      },
      grid: {
        top: 12,
        right: 16,
        bottom: field2 ? 54 : 12,
        left: 48
      },
      xAxis: {
        type: 'category',
        data: timeData,
        boundaryGap: false,
        axisLine: { lineStyle: { color: colors.axisLine } },
        axisTick: { show: false },
        axisLabel: {
          color: colors.axisLabel,
          fontSize: 10,
          rotate: 0,
          interval: 'auto'
        }
      },
      yAxis: {
        type: 'value',
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: colors.splitLine } },
        axisLabel: { color: colors.axisLabel, fontSize: 10 }
      },
      series: seriesList
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

export default DockerAreaChart;

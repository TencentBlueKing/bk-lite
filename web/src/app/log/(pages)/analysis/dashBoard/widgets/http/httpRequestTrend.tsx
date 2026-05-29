import React, { useMemo } from 'react';
import ReactEcharts from 'echarts-for-react';
import { Empty, Spin } from 'antd';
import { ChartDataTransformer } from '@/app/log/utils/chartDataTransform';
import useChartColors from '../docker/useChartColors';
import { createSoftLineArea, createVerticalBarGradient } from '../chartStyle';

const trimTrailingZeros = (value: string) =>
  value.replace(/\.0+$|(?<=\.\d*[1-9])0+$/g, '');

const formatCompactNumber = (value: number): string => {
  if (!isFinite(value)) return '--';

  const absValue = Math.abs(value);
  if (absValue >= 1_000_000) {
    return `${trimTrailingZeros((value / 1_000_000).toFixed(absValue >= 10_000_000 ? 1 : 2))}M`;
  }
  if (absValue >= 1_000) {
    return `${trimTrailingZeros((value / 1_000).toFixed(absValue >= 100_000 ? 0 : 1))}k`;
  }
  return Number.isInteger(value)
    ? String(value)
    : trimTrailingZeros(value.toFixed(2));
};

interface HttpRequestTrendProps {
  rawData: any;
  loading?: boolean;
  config?: any;
}

const HttpRequestTrend: React.FC<HttpRequestTrendProps> = ({
  rawData,
  loading = false,
  config
}) => {
  const colors = useChartColors();

  const option = useMemo(() => {
    if (!Array.isArray(rawData) || rawData.length === 0) {
      return null;
    }

    const sortedData = [...rawData].sort(
      (a, b) => new Date(a._time).getTime() - new Date(b._time).getTime()
    );

    const categories = sortedData.map((item) =>
      ChartDataTransformer.formatTimeValue(item._time)
    );

    const reqcount = sortedData.map((item) => Number(item.reqcount || 0));
    const avgDuration = sortedData.map((item) =>
      Number(item.avg_duration || 0)
    );
    const p95Duration = sortedData.map((item) =>
      Number(item.p95_duration || 0)
    );
    const displayMaps = config?.displayMaps || {};

    return {
      animation: false,
      color: [colors.primary, colors.success, colors.warning],
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        appendToBody: true,
        confine: false,
        textStyle: { fontSize: 12 }
      },
      legend: {
        top: 0,
        textStyle: { color: colors.textSecondary, fontSize: 12 }
      },
      grid: {
        top: 36,
        left: 18,
        right: 18,
        bottom: 20,
        containLabel: true
      },
      xAxis: {
        type: 'category',
        data: categories,
        axisLabel: {
          color: colors.axisLabel,
          fontSize: 11,
          hideOverlap: true,
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
            color: colors.axisLabel,
            hideOverlap: true,
            formatter: (value: number) => formatCompactNumber(value)
          },
          splitLine: { lineStyle: { color: colors.splitLine } }
        },
        {
          type: 'value',
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: {
            color: colors.axisLabel,
            formatter: (value: number) =>
              `${value.toFixed(value >= 100 ? 0 : 1)} ms`
          },
          splitLine: { show: false }
        }
      ],
      series: [
        {
          name: displayMaps.barLabel || 'Requests',
          type: 'bar',
          data: reqcount,
          yAxisIndex: 0,
          barMaxWidth: 16,
          itemStyle: {
            borderRadius: [4, 4, 0, 0],
            color: createVerticalBarGradient(colors.primary)
          },
          emphasis: {
            itemStyle: {
              color: createVerticalBarGradient(colors.primary)
            }
          }
        },
        {
          name: displayMaps.avgLabel || 'Avg',
          type: 'line',
          data: avgDuration,
          yAxisIndex: 1,
          smooth: true,
          symbol: 'none',
          lineStyle: { width: 2, color: colors.success },
          areaStyle: createSoftLineArea(colors.success)
        },
        {
          name: displayMaps.p95Label || 'P95',
          type: 'line',
          data: p95Duration,
          yAxisIndex: 1,
          smooth: true,
          symbol: 'none',
          lineStyle: {
            width: 2,
            color: colors.warning
          },
          areaStyle: createSoftLineArea(colors.warning)
        }
      ]
    };
  }, [config?.displayMaps, colors, rawData]);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Spin size="small" />
      </div>
    );
  }

  if (!option) {
    return (
      <div className="h-full flex items-center justify-center">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </div>
    );
  }

  return (
    <ReactEcharts option={option} style={{ height: '100%', width: '100%' }} />
  );
};

export default HttpRequestTrend;

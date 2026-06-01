import React, { useMemo } from 'react';
import ReactEcharts from 'echarts-for-react';
import { Empty, Spin } from 'antd';
import useChartColors from '../docker/useChartColors';
import { createVerticalBarGradient } from '../chartStyle';

const trimTrailingZeros = (value: string) =>
  value.replace(/\.0+$|(?<=\.\d*[1-9])0+$/g, '');

const toNumber = (value: unknown) => {
  const num = parseFloat(String(value ?? 0));
  return Number.isNaN(num) ? 0 : num;
};

const HttpLatencyBar: React.FC<any> = ({
  rawData,
  loading = false,
  config
}) => {
  const colors = useChartColors();

  const option = useMemo(() => {
    if (!Array.isArray(rawData) || rawData.length === 0) {
      return null;
    }

    const summary = rawData[0] || {};
    const buckets = config?.displayMaps?.buckets || [];
    const normalized = buckets.map(
      (bucket: { field: string; label: string }) => ({
        name: bucket.label,
        value: Math.max(toNumber(summary[bucket.field]), 0)
      })
    );
    const total = normalized.reduce(
      (sum: number, item: { value: number }) => sum + item.value,
      0
    );
    const percentData = normalized.map((item: { value: number }) =>
      total > 0 ? (item.value / total) * 100 : 0
    );

    return {
      animation: false,
      color: [colors.primary],
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        appendToBody: true,
        confine: false,
        textStyle: { fontSize: 12 },
        formatter: (
          params: Array<{ axisValue: string; data: number; dataIndex: number }>
        ) => {
          const item = params?.[0];
          if (!item) return '';

          const count = normalized[item.dataIndex]?.value || 0;
          return `${item.axisValue}<br/>请求数占比 <b>${trimTrailingZeros(item.data.toFixed(1))}%</b><br/>请求数 <b>${count.toLocaleString()}</b>`;
        }
      },
      grid: {
        top: 12,
        left: 18,
        right: 18,
        bottom: 20,
        containLabel: true
      },
      xAxis: {
        type: 'category',
        data: normalized.map((item: { name: string }) => item.name),
        axisLabel: {
          color: colors.axisLabel,
          fontSize: 11,
          interval: 'auto',
          hideOverlap: true,
          rotate: normalized.length > 6 ? 18 : 0
        },
        axisLine: { lineStyle: { color: colors.axisLine } },
        axisTick: { show: false }
      },
      yAxis: {
        type: 'value',
        min: 0,
        max: (value: { max: number }) => {
          if (value.max <= 0) return 100;
          return Math.min(100, Math.ceil(value.max / 10) * 10);
        },
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: colors.axisLabel,
          formatter: (value: number) =>
            `${trimTrailingZeros(value.toFixed(0))}%`
        },
        splitLine: { lineStyle: { color: colors.splitLine } }
      },
      series: [
        {
          type: 'bar',
          data: percentData,
          barMaxWidth: 16,
          itemStyle: {
            color: createVerticalBarGradient(colors.primary),
            borderRadius: [4, 4, 0, 0]
          },
          emphasis: {
            itemStyle: {
              color: createVerticalBarGradient(colors.primary)
            }
          }
        }
      ]
    };
  }, [colors, config?.displayMaps?.buckets, rawData]);

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

export default HttpLatencyBar;

import React, { useMemo } from 'react';
import ReactEcharts from 'echarts-for-react';
import { Empty, Spin } from 'antd';
import { ChartDataTransformer } from '@/app/log/utils/chartDataTransform';
import useChartColors from '../docker/useChartColors';
import { createSoftLineArea } from '../chartStyle';

interface ElasticsearchTrendProps {
  rawData: any;
  loading?: boolean;
}

const formatAxisValue = (value: number) => {
  if (!Number.isFinite(value)) return '--';
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(0)}k`;
  return String(Math.round(value));
};

const ElasticsearchTrend: React.FC<ElasticsearchTrendProps> = ({
  rawData,
  loading = false
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

    return {
      animation: false,
      color: [colors.primary, colors.danger, colors.warning, colors.series[5]],
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        appendToBody: true,
        confine: false,
        textStyle: { fontSize: 12 }
      },
      legend: {
        top: 0,
        left: 18,
        textStyle: { color: colors.textSecondary, fontSize: 12 },
        itemWidth: 12,
        itemHeight: 4,
        icon: 'rect'
      },
      grid: {
        top: 34,
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
          interval: 'auto',
          hideOverlap: true
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
            formatter: (value: number) => formatAxisValue(value)
          },
          splitLine: { lineStyle: { color: colors.splitLine } }
        },
        {
          type: 'value',
          minInterval: 1,
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: {
            color: colors.axisLabel,
            formatter: (value: number) => formatAxisValue(value)
          },
          splitLine: { show: false }
        }
      ],
      series: [
        {
          name: '总日志数',
          type: 'line',
          data: sortedData.map((item) => Number(item.total_count || 0)),
          yAxisIndex: 0,
          smooth: true,
          symbol: 'none',
          lineStyle: { width: 2.5, color: colors.primary },
          areaStyle: createSoftLineArea(colors.primary)
        },
        {
          name: 'Error 日志数',
          type: 'line',
          data: sortedData.map((item) => Number(item.error_count || 0)),
          yAxisIndex: 1,
          smooth: true,
          symbol: 'none',
          lineStyle: { width: 2, color: colors.danger },
          areaStyle: createSoftLineArea(colors.danger)
        },
        {
          name: 'Warn 日志数',
          type: 'line',
          data: sortedData.map((item) => Number(item.warn_count || 0)),
          yAxisIndex: 1,
          smooth: true,
          symbol: 'none',
          lineStyle: { width: 2, color: colors.warning },
          areaStyle: createSoftLineArea(colors.warning)
        },
        {
          name: '慢日志数',
          type: 'line',
          data: sortedData.map((item) => Number(item.slow_count || 0)),
          yAxisIndex: 1,
          smooth: true,
          symbol: 'none',
          lineStyle: { width: 2, color: colors.series[5] },
          areaStyle: createSoftLineArea(colors.series[5])
        }
      ]
    };
  }, [colors, rawData]);

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

  return <ReactEcharts option={option} style={{ height: '100%', width: '100%' }} />;
};

export default ElasticsearchTrend;

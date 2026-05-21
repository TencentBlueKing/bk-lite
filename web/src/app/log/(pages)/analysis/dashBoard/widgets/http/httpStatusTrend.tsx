import React, { useMemo } from 'react';
import ReactEcharts from 'echarts-for-react';
import { Empty, Spin } from 'antd';
import { ChartDataTransformer } from '@/app/log/utils/chartDataTransform';
import useChartColors from '../docker/useChartColors';
import {
  type HttpStatusCategoryKey,
  getHttpStatusCategory
} from './statusCodeCategory';

type HttpStatusTrendPoint = {
  _time: string;
} & Record<HttpStatusCategoryKey, number>;

const toNumber = (value: unknown) => {
  const num = Number.parseFloat(String(value ?? 0));
  return Number.isNaN(num) ? 0 : num;
};

const HttpStatusTrend: React.FC<any> = ({
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
    const labels = config?.displayMaps?.labels || {};
    const groupedData = sortedData.reduce(
      (acc: Record<string, HttpStatusTrendPoint>, item) => {
        const timeKey = String(item._time || '');
        const category = getHttpStatusCategory(
          item['http.response.status_code']
        );

        if (!timeKey) {
          return acc;
        }

        if (!acc[timeKey]) {
          acc[timeKey] = {
            _time: timeKey,
            status_2xx: 0,
            status_3xx: 0,
            status_4xx: 0,
            status_5xx: 0,
            status_other: 0
          };
        }

        acc[timeKey][category] =
          toNumber(acc[timeKey][category]) + toNumber(item.reqcount);
        return acc;
      },
      {}
    );
    const normalizedData = (
      Object.values(groupedData) as HttpStatusTrendPoint[]
    ).sort((a, b) => new Date(a._time).getTime() - new Date(b._time).getTime());
    const categories = normalizedData.map((item) =>
      ChartDataTransformer.formatTimeValue(item._time)
    );

    const seriesConfigs = [
      {
        key: 'status_2xx',
        label: labels.status_2xx || '2xx',
        color: colors.success
      },
      {
        key: 'status_3xx',
        label: labels.status_3xx || '3xx',
        color: colors.primary
      },
      {
        key: 'status_4xx',
        label: labels.status_4xx || '4xx',
        color: colors.warning
      },
      {
        key: 'status_5xx',
        label: labels.status_5xx || '5xx',
        color: colors.danger
      },
      {
        key: 'status_other',
        label: labels.status_other || 'Other',
        color: colors.series[5] || colors.primary
      }
    ];

    return {
      animation: false,
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
      yAxis: {
        type: 'value',
        minInterval: 1,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: colors.axisLabel },
        splitLine: { lineStyle: { color: colors.splitLine } }
      },
      series: seriesConfigs.map((seriesConfig) => ({
        name: seriesConfig.label,
        type: 'line',
        data: normalizedData.map((item) => Number(item[seriesConfig.key] || 0)),
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 2, color: seriesConfig.color }
      }))
    };
  }, [colors, config?.displayMaps?.labels, rawData]);

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

export default HttpStatusTrend;

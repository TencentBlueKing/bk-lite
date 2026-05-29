import React, { useMemo } from 'react';
import ReactEcharts from 'echarts-for-react';
import { Empty, Spin } from 'antd';
import { ChartDataTransformer } from '@/app/log/utils/chartDataTransform';
import useChartColors from '../docker/useChartColors';
import { createSoftLineArea, createVerticalBarGradient } from '../chartStyle';

interface FileIntegrityTrendProps {
  rawData: any;
  loading?: boolean;
}

const formatAxisValue = (value: number) => {
  if (!Number.isFinite(value)) return '--';
  if (Math.abs(value) >= 1000) return `${(value / 1000).toFixed(1)}k`;
  return String(Math.round(value));
};

const FileIntegrityTrend: React.FC<FileIntegrityTrendProps> = ({
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

    return {
      animation: false,
      color: [colors.success, colors.series[5] || '#8B5CF6', colors.danger, colors.warning],
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
        data: sortedData.map((item) =>
          ChartDataTransformer.formatTimeValue(item._time)
        ),
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
          name: '新增',
          type: 'bar',
          data: sortedData.map((item) => Number(item.created_count || 0)),
          barMaxWidth: 10,
          itemStyle: {
            color: createVerticalBarGradient(colors.success),
            borderRadius: [3, 3, 0, 0]
          }
        },
        {
          name: '修改',
          type: 'bar',
          data: sortedData.map((item) => Number(item.updated_count || 0)),
          barMaxWidth: 10,
          itemStyle: {
            color: createVerticalBarGradient(colors.series[5] || '#8B5CF6'),
            borderRadius: [3, 3, 0, 0]
          }
        },
        {
          name: '删除',
          type: 'bar',
          data: sortedData.map((item) => Number(item.deleted_count || 0)),
          barMaxWidth: 10,
          itemStyle: {
            color: createVerticalBarGradient(colors.danger),
            borderRadius: [3, 3, 0, 0]
          }
        },
        {
          name: '权限变更',
          type: 'line',
          yAxisIndex: 1,
          data: sortedData.map((item) => Number(item.permission_count || 0)),
          smooth: true,
          symbol: 'none',
          lineStyle: { width: 2, color: colors.warning },
          areaStyle: createSoftLineArea(colors.warning)
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

export default FileIntegrityTrend;

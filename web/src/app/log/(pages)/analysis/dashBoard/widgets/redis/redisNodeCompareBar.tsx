import React, { useMemo } from 'react';
import ReactEcharts from 'echarts-for-react';
import { Empty } from 'antd';
import useChartColors from '../docker/useChartColors';

// 节点日志量 vs 错误数 双系列横向柱状图
// rawData 期望字段：node_ip, log_count, err_count

interface RedisNodeCompareBarProps {
  rawData: any;
  loading?: boolean;
}

const normLabel = (v: unknown): string => {
  if (v === null || v === undefined || v === '') return '(空)';
  return String(v);
};

const RedisNodeCompareBar: React.FC<RedisNodeCompareBarProps> = ({
  rawData,
  loading = false
}) => {
  const colors = useChartColors();

  const chartOption = useMemo(() => {
    if (!Array.isArray(rawData) || rawData.length === 0) return null;

    const cats = rawData.map((r: any) => normLabel(r['node_ip']));
    const logVals = rawData.map((r: any) => {
      const n = parseFloat(String(r['log_count'] ?? 0));
      return isNaN(n) ? 0 : n;
    });
    const errVals = rawData.map((r: any) => {
      const n = parseFloat(String(r['err_count'] ?? 0));
      return isNaN(n) ? 0 : n;
    });

    return {
      tooltip: {
        trigger: 'axis',
        appendToBody: true,
        confine: false,
        backgroundColor: colors.tooltipBg,
        borderColor: colors.tooltipBorder,
        textStyle: { color: colors.textPrimary, fontSize: 12 },
        axisPointer: { type: 'shadow' }
      },
      legend: {
        top: 4,
        right: 8,
        itemWidth: 12,
        itemHeight: 12,
        textStyle: { color: colors.textSecondary, fontSize: 11 }
      },
      grid: { left: 8, right: 32, top: 28, bottom: 8, containLabel: true },
      xAxis: {
        type: 'value',
        axisLabel: { color: colors.axisLabel, fontSize: 11 },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: colors.splitLine, type: 'dashed' } }
      },
      yAxis: {
        type: 'category',
        data: [...cats].reverse(),
        axisLine: { lineStyle: { color: colors.axisLine } },
        axisTick: { show: false },
        axisLabel: {
          color: colors.axisLabel,
          fontSize: 11,
          width: 110,
          overflow: 'truncate',
          formatter: (v: string) => (v.length > 16 ? `${v.slice(0, 15)}…` : v)
        }
      },
      series: [
        {
          name: '日志量',
          type: 'bar',
          data: [...logVals].reverse(),
          barMaxWidth: 14,
          itemStyle: { color: colors.series[0], borderRadius: [0, 3, 3, 0] },
          label: { show: false }
        },
        {
          name: '错误数',
          type: 'bar',
          data: [...errVals].reverse(),
          barMaxWidth: 14,
          itemStyle: { color: colors.series[4], borderRadius: [0, 3, 3, 0] },
          label: { show: false }
        }
      ]
    };
  }, [rawData, colors]);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div
          className="w-5 h-5 rounded-full border-2 border-t-transparent animate-spin"
          style={{
            borderColor: `${colors.primary}33`,
            borderTopColor: 'transparent'
          }}
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

export default RedisNodeCompareBar;

import React, { useMemo } from 'react';
import ReactEcharts from 'echarts-for-react';
import { Empty } from 'antd';
import useChartColors from '../docker/useChartColors';
import { createHorizontalBarGradient } from '../chartStyle';

// Redis 专属横向柱状图，用于实例/命令/case 维度分析
// displayMaps.key   = 类目字段名（如 node_ip / redis_cmd / err_case）
// displayMaps.value = 数值字段名（如 log_count / err_count）

interface RedisInstanceBarProps {
  rawData: any;
  loading?: boolean;
  config?: {
    displayMaps?: {
      key: string;
      value: string;
    };
  };
}

const normLabel = (v: unknown): string => {
  if (v === null || v === undefined || v === '') return '(空)';
  return String(v);
};

const RedisInstanceBar: React.FC<RedisInstanceBarProps> = ({
  rawData,
  loading = false,
  config
}) => {
  const colors = useChartColors();
  const keyField = config?.displayMaps?.key || 'node_ip';
  const valueField = config?.displayMaps?.value || 'log_count';

  const chartOption = useMemo(() => {
    if (!Array.isArray(rawData) || rawData.length === 0) return null;

    const cats = rawData.map((r: any) => normLabel(r[keyField]));
    const vals = rawData.map((r: any) => {
      const n = parseFloat(String(r[valueField] ?? 0));
      return isNaN(n) ? 0 : n;
    });

    const barColor = colors.series[0]; // 主蓝色，和 Docker 一致

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
      grid: { left: 8, right: 32, top: 8, bottom: 8, containLabel: true },
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
          width: 120,
          overflow: 'truncate',
          formatter: (v: string) => (v.length > 18 ? `${v.slice(0, 17)}…` : v)
        }
      },
      series: [
        {
          type: 'bar',
          data: [...vals].reverse(),
          barMaxWidth: 16,
          itemStyle: {
            color: createHorizontalBarGradient(barColor),
            borderRadius: [0, 3, 3, 0]
          },
          label: {
            show: true,
            position: 'right',
            fontSize: 11,
            color: colors.textSecondary
          }
        }
      ]
    };
  }, [rawData, keyField, valueField, colors]);

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

export default RedisInstanceBar;

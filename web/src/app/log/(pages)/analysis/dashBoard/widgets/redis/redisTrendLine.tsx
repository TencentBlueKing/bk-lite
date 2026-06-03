import React, { useMemo } from 'react';
import ReactEcharts from 'echarts-for-react';
import { Empty } from 'antd';
import useChartColors from '../docker/useChartColors';
import { createSoftLineArea } from '../chartStyle';

// Redis 日志量趋势折线图（双系列：总量 + 错误量）
// displayMaps.key        = 时间字段（_time）
// displayMaps.totalField = 总量字段名
// displayMaps.errField   = 错误量字段名（可选）
// displayMaps.totalLabel / errLabel = 图例标签

interface RedisTrendLineProps {
  rawData: any;
  loading?: boolean;
  config?: {
    displayMaps?: {
      key?: string;
      totalField?: string;
      errField?: string;
      totalLabel?: string;
      errLabel?: string;
    };
  };
}

const axisFormatter = (v: number): string => {
  if (Math.abs(v) >= 1_000_000) return (v / 1_000_000).toFixed(1) + 'M';
  if (Math.abs(v) >= 1_000) return (v / 1_000).toFixed(1) + 'k';
  return String(v);
};

const formatTs = (v: unknown): string => {
  if (!v) return '';
  try {
    const d = new Date(String(v));
    return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  } catch {
    return String(v);
  }
};

const RedisTrendLine: React.FC<RedisTrendLineProps> = ({
  rawData,
  loading = false,
  config
}) => {
  const colors = useChartColors();
  const dm = config?.displayMaps || {};
  const keyField = dm.key || '_time';
  const totalField = dm.totalField || 'total_count';
  const errField = dm.errField || 'err_count';
  const totalLabel = dm.totalLabel || '日志总量';
  const errLabel = dm.errLabel || 'ERR 错误';

  const chartOption = useMemo(() => {
    if (!Array.isArray(rawData) || rawData.length === 0) return null;

    const xData = rawData.map((r: any) => formatTs(r[keyField]));
    const totalData = rawData.map((r: any) => {
      const n = parseFloat(String(r[totalField] ?? 0));
      return isNaN(n) ? 0 : n;
    });
    const errData = rawData.map((r: any) => {
      const n = parseFloat(String(r[errField] ?? 0));
      return isNaN(n) ? 0 : n;
    });
    const hasErr = errData.some((v: number) => v > 0);

    const color1 = colors.series[0]; // 蓝 — 总量
    const color2 = colors.series[4]; // 红 — 错误

    const series: any[] = [
      {
        name: totalLabel,
        type: 'line',
        data: totalData,
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 2, color: color1 },
        itemStyle: { color: color1 },
        areaStyle: createSoftLineArea(color1),
        yAxisIndex: 0
      }
    ];

    const yAxes: any[] = [
      {
        type: 'value',
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: colors.splitLine } },
        axisLabel: {
          color: colors.axisLabel,
          fontSize: 10,
          formatter: axisFormatter
        }
      }
    ];

    if (hasErr) {
      series.push({
        name: errLabel,
        type: 'line',
        data: errData,
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 2, color: color2 },
        itemStyle: { color: color2 },
        areaStyle: createSoftLineArea(color2),
        yAxisIndex: 1
      });
      yAxes.push({
        type: 'value',
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: {
          color: colors.axisLabel,
          fontSize: 10,
          formatter: axisFormatter
        }
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
        show: hasErr,
        top: 4,
        left: 8,
        textStyle: { color: colors.textSecondary, fontSize: 11 },
        itemWidth: 12,
        itemHeight: 4,
        icon: 'rect'
      },
      grid: {
        top: hasErr ? 36 : 16,
        right: hasErr ? 52 : 16,
        bottom: 24,
        left: 52
      },
      xAxis: {
        type: 'category',
        data: xData,
        boundaryGap: false,
        axisLine: { lineStyle: { color: colors.axisLine } },
        axisTick: { show: false },
        axisLabel: { color: colors.axisLabel, fontSize: 10, interval: 'auto' }
      },
      yAxis: yAxes,
      series
    };
  }, [
    rawData,
    config,
    colors,
    keyField,
    totalField,
    errField,
    totalLabel,
    errLabel
  ]);

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

export default RedisTrendLine;

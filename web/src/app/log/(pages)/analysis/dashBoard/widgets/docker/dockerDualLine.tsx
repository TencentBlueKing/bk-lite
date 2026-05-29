import React, { useMemo } from 'react';
import ReactEcharts from 'echarts-for-react';
import { Empty } from 'antd';
import useChartColors from './useChartColors';
import { createSoftLineArea } from '../chartStyle';

/**
 * DockerDualLine — 双折线 + 双Y轴
 * 左轴对应 field1（barField），右轴对应 field2（lineField）。
 * 两条线各自独立Y轴，适用于数量级差异较大的场景（如日志总量 vs 错误量）。
 */

interface DockerDualLineProps {
  rawData: any;
  loading?: boolean;
  config?: any;
}

/** 轴标签单位换算（k/M） */
const axisFormatter = (v: number): string => {
  if (Math.abs(v) >= 1_000_000) return (v / 1_000_000).toFixed(1) + 'M';
  if (Math.abs(v) >= 1_000) return (v / 1_000).toFixed(1) + 'k';
  return String(v);
};

const DockerDualLine: React.FC<DockerDualLineProps> = ({
  rawData,
  loading = false,
  config
}) => {
  const colors = useChartColors();

  const chartOption = useMemo(() => {
    if (!rawData || !Array.isArray(rawData) || rawData.length === 0)
      return null;

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

    const color1 = colors.series[0]; // 蓝
    const color2 = colors.series[4]; // 红（danger）

    const seriesList: any[] = [
      {
        name: label1,
        type: 'line',
        yAxisIndex: 0,
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 2, color: color1 },
        itemStyle: { color: color1 },
        areaStyle: createSoftLineArea(color1),
        data: series1Data
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

    if (field2) {
      const series2Data = rawData.map((item: any) => {
        const v = parseFloat(item[field2]);
        return isNaN(v) ? 0 : v;
      });
      seriesList.push({
        name: label2,
        type: 'line',
        yAxisIndex: 1,
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 2, color: color2 },
        itemStyle: { color: color2 },
        areaStyle: createSoftLineArea(color2),
        data: series2Data
      });
      yAxes.push({
        type: 'value',
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { show: false }, // 右轴不画分割线，避免与左轴重叠
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
        top: 4,
        left: 8,
        textStyle: { color: colors.textSecondary, fontSize: 11 },
        itemWidth: 12,
        itemHeight: 4,
        icon: 'rect'
      },
      grid: {
        top: 36,
        right: field2 ? 52 : 16, // 右轴有刻度时右侧留空间
        bottom: 24,
        left: 52
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
          interval: 'auto'
        }
      },
      yAxis: yAxes,
      series: seriesList
    };
  }, [rawData, config, colors]);

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

export default DockerDualLine;

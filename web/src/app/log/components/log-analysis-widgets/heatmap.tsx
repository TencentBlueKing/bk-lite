import React, { useEffect, useMemo, useState } from 'react';
import ReactEcharts from 'echarts-for-react';
import { ChartDataTransformer } from '@/app/log/components/log-analysis-widgets/runtime';
import ChartSurface from '@/components/chart-surface';
import useChartColors from '@/hooks/useChartColors';

export interface LogAnalysisHeatmapProps {
  rawData: any;
  loading?: boolean;
  config?: any;
  onReady?: (ready: boolean) => void;
}

const LogAnalysisHeatmap: React.FC<LogAnalysisHeatmapProps> = ({
  rawData,
  loading = false,
  config,
  onReady,
}) => {
  const [isDataReady, setIsDataReady] = useState(false);
  const colors = useChartColors();

  const heatmapData = useMemo(() => {
    if (!Array.isArray(rawData) || !rawData.length) {
      return {
        xAxis: [],
        yAxis: [],
        values: [],
        max: 0,
      };
    }

    const timeKey = config?.displayMaps?.time || '_time';
    const categoryKey = config?.displayMaps?.category || 'container_name';
    const valueKey = config?.displayMaps?.value || 'errcount';

    const rows = rawData
      .filter((item) => item?.[timeKey] && item?.[categoryKey])
      .sort(
        (a, b) =>
          new Date(a[timeKey]).getTime() - new Date(b[timeKey]).getTime(),
      );

    const xAxis = [
      ...new Set(
        rows.map((item) => ChartDataTransformer.formatTimeValue(item[timeKey])),
      ),
    ];
    const categories = new Map<string, number>();

    rows.forEach((item) => {
      const category = String(item[categoryKey]);
      const current = categories.get(category) || 0;
      categories.set(category, current + (Number(item[valueKey]) || 0));
    });

    const yAxis = [...categories.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, config?.limit || 8)
      .map(([name]) => name);

    const values = rows
      .filter((item) => yAxis.includes(String(item[categoryKey])))
      .map((item) => [
        xAxis.indexOf(ChartDataTransformer.formatTimeValue(item[timeKey])),
        yAxis.indexOf(String(item[categoryKey])),
        Number(item[valueKey]) || 0,
      ]);

    return {
      xAxis,
      yAxis,
      values,
      max: Math.max(...values.map((item) => item[2]), 0),
    };
  }, [config, rawData]);

  useEffect(() => {
    if (!loading) {
      const hasData = !!heatmapData.values.length;
      setIsDataReady(hasData);
      onReady?.(hasData);
    }
  }, [heatmapData, loading, onReady]);

  const option = {
    tooltip: {
      confine: false,
      appendToBody: true,
      position: 'top',
      backgroundColor: colors.tooltipBg,
      borderColor: colors.tooltipBorder,
      textStyle: {
        color: colors.textPrimary,
      },
    },
    grid: {
      top: 12,
      left: 64,
      right: 12,
      bottom: 56,
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: heatmapData.xAxis,
      splitArea: { show: false },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: colors.axisLine } },
      axisLabel: {
        fontSize: 11,
        color: colors.axisLabel,
      },
    },
    yAxis: {
      type: 'category',
      data: heatmapData.yAxis,
      splitArea: { show: false },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: colors.axisLine } },
      axisLabel: {
        fontSize: 11,
        color: colors.axisLabel,
      },
    },
    visualMap: {
      show: true,
      min: 0,
      max: heatmapData.max || 1,
      calculable: false,
      orient: 'horizontal',
      left: 'center',
      bottom: 2,
      textStyle: {
        color: colors.textSecondary,
      },
      inRange: {
        color: [
          'color-mix(in srgb, var(--color-primary) 10%, white)',
          'color-mix(in srgb, var(--color-primary) 22%, white)',
          'color-mix(in srgb, var(--color-primary) 42%, white)',
          'var(--color-primary)',
        ],
      },
    },
    series: [
      {
        type: 'heatmap',
        data: heatmapData.values,
        label: {
          show: false,
        },
        emphasis: {
          itemStyle: {
            borderColor: colors.background,
            borderWidth: 1,
          },
        },
      },
    ],
  };

  return (
    <ChartSurface
      loading={loading}
      hasData={isDataReady}
      containerClassName="flex h-full w-full"
      loadingClassName="flex h-full w-full items-center justify-center"
      emptyClassName="flex h-full w-full items-center justify-center"
    >
      <ReactEcharts option={option} style={{ height: '100%', width: '100%' }} />
    </ChartSurface>
  );
};

export default LogAnalysisHeatmap;

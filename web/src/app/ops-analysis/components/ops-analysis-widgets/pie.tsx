import React, { useCallback, useMemo, useRef, useState } from 'react';
import ReactEcharts from 'echarts-for-react';
import {
  ChartDataTransformer,
  getOpsChartTheme,
  randomColorForLegend,
  resolveOpsChartThemeName,
} from '@/app/ops-analysis/components/ops-analysis-widgets/runtime';
import ChartLegend from '@/components/chart-legend';
import { isSameChartLegendSelection } from '@/components/chart-legend/selection';
import ChartWithSidebarLegend from '@/components/chart-with-sidebar-legend';
import { renderEChartsTooltipCard } from '@/components/echarts-tooltip-card';
import type { ValueConfig } from '@/app/ops-analysis/components/ops-analysis-widgets';
import { useEchartsFinishedReady } from '@/app/ops-analysis/hooks/useEchartsFinishedReady';
import { formatVisibleChartValue } from '@/app/ops-analysis/utils/chartValueFormat';

export interface OpsAnalysisPieProps {
  rawData: any;
  loading?: boolean;
  onReady?: (ready: boolean) => void;
  config?: ValueConfig;
}

const OpsAnalysisPie: React.FC<OpsAnalysisPieProps> = ({
  rawData,
  loading = false,
  onReady,
  config,
}) => {
  const chartRef = useRef<any>(null);
  const themeName = resolveOpsChartThemeName();
  const chartTheme = useMemo(() => getOpsChartTheme(themeName), [themeName]);
  const chartColors = useMemo(
    () => randomColorForLegend(themeName),
    [themeName],
  );
  const [legendSelected, setLegendSelected] = useState<Record<string, boolean>>({});

  const handleLegendChange = useCallback((selected: Record<string, boolean>) => {
    setLegendSelected((prev) =>
      isSameChartLegendSelection(prev, selected) ? prev : selected,
    );
  }, []);

  const chartData = useMemo(
    () => ChartDataTransformer.transformToPieData(rawData),
    [rawData],
  );
  const isDataReady = chartData.some(
    (item) => Number.isFinite(item.value) && item.value > 0,
  );
  const showLegend = isDataReady;
  const { onEvents } = useEchartsFinishedReady({
    loading,
    isDataReady,
    onReady,
  });

  const option = useMemo(() => ({
    color: chartColors,
    animation: true,
    calculable: true,
    title: { show: false },
    tooltip: {
      trigger: 'item',
      enterable: true,
      confine: true,
      backgroundColor: 'transparent',
      borderWidth: 0,
      borderColor: 'transparent',
      extraCssText: 'box-shadow:none;padding:0;background:transparent;',
      textStyle: {
        fontSize: 12,
        color: chartTheme.tooltipTextColor,
      },
      formatter: function (params: any) {
        const percent = params.percent || 0;
        return renderEChartsTooltipCard({
          title: params.seriesName || '',
          rows: [
            {
              key: params.name,
              color: params.color,
              markerShape: 'circle',
              label: params.name || '--',
              value: `${formatVisibleChartValue(params.value, config)} (${percent.toFixed(1)}%)`,
            },
          ],
        });
      },
    },
    legend: {
      show: false,
      selected: legendSelected,
    },
    series: [
      {
        name: '',
        type: 'pie',
        center: ['50%', '50%'],
        radius: ['50%', '78%'],
        avoidLabelOverlap: false,
        selectedMode: 'single',
        label: {
          show: true,
          position: 'center',
          formatter: function () {
            const total = (chartData || []).reduce(
              (sum: number, item: any) => sum + item.value,
              0,
            );
            return `{title|总数}\n{value|${formatVisibleChartValue(total, config)}}`;
          },
          rich: {
            title: {
              fontSize: 14,
              color: chartTheme.pieTitleColor,
              lineHeight: 20,
            },
            value: {
              fontSize: 24,
              fontWeight: 'bold',
              color: chartTheme.pieValueColor,
              lineHeight: 32,
            },
          },
        },
        labelLine: {
          show: false,
          length: 10,
          length2: 15,
          smooth: true,
        },
        itemStyle: {
          borderRadius: 2,
          borderColor: chartTheme.pieBorderColor,
          borderWidth: 1,
        },
        emphasis: {
          focus: 'none',
          scaleSize: 5,
        },
        data: chartData || [],
      },
    ],
  }), [chartColors, chartData, chartTheme, config, legendSelected]);

  return (
    <ChartWithSidebarLegend
      chart={
        <ReactEcharts
          ref={chartRef}
          option={option}
          notMerge={true}
          onEvents={onEvents}
          style={{ height: '100%', width: '100%' }}
        />
      }
      legend={
        <ChartLegend
          data={chartData.map((item: any) => ({
            name: item.name,
            value: item.value,
          }))}
          colors={chartColors}
          layout="vertical"
          showPercent={true}
          onSelectionChange={handleLegendChange}
        />
      }
      legendVisible={showLegend}
      surfaceProps={{
        loading,
        hasData: !!(isDataReady && chartData && chartData.length > 0),
        containerClassName: 'flex h-full min-h-0 w-full',
        loadingClassName: 'flex h-full w-full items-center justify-center',
        emptyClassName: 'flex h-full w-full items-center justify-center',
      }}
    />
  );
};

export default OpsAnalysisPie;

import React, { useCallback, useEffect, useRef, useState } from 'react';
import ReactEcharts from 'echarts-for-react';
import {
  ChartDataTransformer,
  getOpsChartTheme,
  randomColorForLegend,
  resolveOpsChartThemeName,
} from '@/app/ops-analysis/components/ops-analysis-widgets/runtime';
import ChartLegend from '@/components/chart-legend';
import ChartWithSidebarLegend from '@/components/chart-with-sidebar-legend';
import { renderEChartsTooltipCard } from '@/components/echarts-tooltip-card';

export interface OpsAnalysisPieProps {
  rawData: any;
  loading?: boolean;
  onReady?: (ready: boolean) => void;
}

const OpsAnalysisPie: React.FC<OpsAnalysisPieProps> = ({
  rawData,
  loading = false,
  onReady,
}) => {
  const chartRef = useRef<any>(null);
  const themeName = resolveOpsChartThemeName();
  const chartTheme = getOpsChartTheme(themeName);
  const chartColors = randomColorForLegend(themeName);
  const [legendSelected, setLegendSelected] = useState<Record<string, boolean>>({});

  const handleLegendChange = useCallback((selected: Record<string, boolean>) => {
    setLegendSelected(selected);
  }, []);

  const chartData = ChartDataTransformer.transformToPieData(rawData);
  const isDataReady = chartData.length > 0;
  const showLegend = chartData.length > 0;

  useEffect(() => {
    if (!loading) {
      onReady?.(isDataReady);
    }
  }, [isDataReady, loading, onReady]);

  const option: any = {
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
              value: `${params.value} (${percent.toFixed(1)}%)`,
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
            return `{title|总数}\n{value|${total}}`;
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
  };

  return (
    <ChartWithSidebarLegend
      chart={
        <ReactEcharts
          ref={chartRef}
          option={option}
          notMerge={true}
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
        containerClassName: 'flex h-full w-full',
        loadingClassName: 'flex h-full w-full items-center justify-center',
        emptyClassName: 'flex h-full w-full items-center justify-center',
      }}
    />
  );
};

export default OpsAnalysisPie;

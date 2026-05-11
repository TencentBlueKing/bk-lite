import React, { useMemo } from 'react';
import ReactEcharts from 'echarts-for-react';
import { Empty } from 'antd';
import useChartColors from './useChartColors';
import { formatNumericValue } from '@/app/log/utils/common';

interface DockerDonutChartProps {
  rawData: any;
  loading?: boolean;
  config?: any;
}

const DockerDonutChart: React.FC<DockerDonutChartProps> = ({
  rawData,
  loading = false,
  config
}) => {
  const colors = useChartColors();

  const { chartOption, total } = useMemo(() => {
    if (!rawData || !Array.isArray(rawData) || rawData.length === 0) {
      return { chartOption: null, total: 0 };
    }

    const displayMaps = config?.displayMaps || {};
    const nameField = displayMaps.key || 'name';
    const valueField = displayMaps.value || 'count';

    const pieData = rawData.map((item: any, idx: number) => ({
      name: item[nameField] || `item-${idx}`,
      value: parseFloat(item[valueField]) || 0
    }));
    const visiblePieData = pieData.filter((item: any) => item.value > 0);
    const finalPieData = visiblePieData.length > 0 ? visiblePieData : pieData;

    const totalVal = finalPieData.reduce((sum: number, d: any) => sum + d.value, 0);
    const showLegend = finalPieData.length > 1;

    return {
      total: totalVal,
      chartOption: {
        tooltip: {
          trigger: 'item',
          appendToBody: true,
          confine: false,
          backgroundColor: colors.tooltipBg,
          borderColor: colors.tooltipBorder,
          textStyle: { color: colors.textPrimary, fontSize: 12 },
          formatter: (params: any) => {
            return `${params.marker} ${params.name}: ${formatNumericValue(params.value)} (${params.percent}%)`;
          }
        },
        legend: showLegend ? {
          orient: 'vertical',
          right: 8,
          top: 'center',
          textStyle: { color: colors.textSecondary, fontSize: 11 },
          itemWidth: 10,
          itemHeight: 10,
          itemGap: 8
        } : { show: false },
        series: [
          {
            type: 'pie',
            radius: ['55%', '78%'],
            center: showLegend ? ['35%', '50%'] : ['50%', '50%'],
            avoidLabelOverlap: false,
            label: { show: false },
            emphasis: {
              label: { show: false },
              scaleSize: 4
            },
            labelLine: { show: false },
            data: finalPieData,
            color: colors.series
          }
        ]
      }
    };
  }, [rawData, config, colors]);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div
          className="w-5 h-5 rounded-full border-2 border-t-transparent animate-spin"
          style={{ borderColor: `${colors.primary}33`, borderTopColor: 'transparent' }}
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
    <div className="relative h-full w-full">
      <ReactEcharts
        option={chartOption}
        style={{ height: '100%', width: '100%' }}
        opts={{ renderer: 'canvas' }}
        notMerge
      />
      {/* 中心汇总数字 */}
      <div
        className="absolute pointer-events-none flex flex-col items-center justify-center"
        style={{
          left: chartOption.legend?.show === false ? '50%' : '35%',
          top: '50%',
          transform: 'translate(-50%, -50%)'
        }}
      >
        <span
          className="text-lg font-bold leading-none"
          style={{ color: colors.textPrimary }}
        >
          {formatNumericValue(total)}
        </span>
        <span
          className="text-[10px] mt-0.5"
          style={{ color: colors.textTertiary }}
        >
          Total
        </span>
      </div>
    </div>
  );
};

export default DockerDonutChart;

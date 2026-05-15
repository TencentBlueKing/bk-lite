import React, { useMemo, useRef, useState, useEffect } from 'react';
import ReactEcharts from 'echarts-for-react';
import { Empty } from 'antd';
import useChartColors from './useChartColors';
import { formatNumericValue } from '@/app/log/utils/common';

const trimTrailingZeros = (value: string) =>
  value.replace(/\.0+$|(?<=\.\d*[1-9])0+$/g, '');

const formatDonutCenterValue = (value: number): string => {
  if (!isFinite(value)) return '--';

  const absValue = Math.abs(value);

  if (absValue >= 1_000_000) {
    return `${trimTrailingZeros((value / 1_000_000).toFixed(absValue >= 10_000_000 ? 1 : 2))}M`;
  }

  if (absValue >= 1_000) {
    return `${trimTrailingZeros((value / 1_000).toFixed(absValue >= 100_000 ? 0 : 1))}k`;
  }

  return Number.isInteger(value)
    ? String(value)
    : trimTrailingZeros(value.toFixed(2));
};

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
  const containerRef = useRef<HTMLDivElement>(null);
  // 容器尺寸，用于计算绝对像素 radius
  const [size, setSize] = useState({ w: 0, h: 0 });

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const obs = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setSize({
          w: entry.contentRect.width,
          h: entry.contentRect.height
        });
      }
    });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

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

    const totalVal = finalPieData.reduce(
      (sum: number, d: any) => sum + d.value,
      0
    );
    const showLegend = finalPieData.length >= 1;

    // 用绝对像素确保圆形不变形
    // 预留 legend 宽度 ~115px（10px icon + 100px text + 5px gap），剩余区域取最小边的一半做半径
    const legendWidth = showLegend ? 115 : 0;
    const chartAreaW = size.w > 0 ? size.w - legendWidth : 200;
    const chartAreaH = size.h > 0 ? size.h - 16 : 180; // 留顶底少量间距
    const minSide = Math.min(chartAreaW, chartAreaH);
    const outerR = Math.max(30, Math.floor(minSide * 0.42));
    const innerR = Math.max(18, Math.floor(outerR * 0.68));

    // center x: 在图表区域居中
    const centerX =
      legendWidth > 0
        ? Math.floor(chartAreaW / 2)
        : Math.floor((size.w || 200) / 2);
    const centerY = Math.floor((size.h || 200) / 2);

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
        legend: showLegend
          ? {
            orient: 'vertical',
            right: 4,
            top: 'center',
            textStyle: { color: colors.textSecondary, fontSize: 11 },
            itemWidth: 10,
            itemHeight: 10,
            itemGap: 6,
            // 固定宽度 + overflow truncate，文字过长自动截断
            width: 100,
            formatter: (name: string) => {
              const item = finalPieData.find((d: any) => d.name === name);
              if (!item) return name;
              const pct =
                totalVal > 0
                  ? ((item.value / totalVal) * 100).toFixed(1)
                  : '0.0';
              return `${name}  ${pct}%`;
            },
            tooltip: {
              show: true,
              formatter: (params: any) => {
                const item = finalPieData.find(
                  (d: any) => d.name === params.name
                );
                if (!item) return params.name;
                const pct =
                  totalVal > 0
                    ? ((item.value / totalVal) * 100).toFixed(2)
                    : '0.00';
                return `${params.name}: ${item.value} (${pct}%)`;
              }
            }
          } 
          : { show: false },
        series: [
          {
            type: 'pie',
            // 绝对像素 radius，彻底防变形
            radius: size.w > 0 ? [innerR, outerR] : ['55%', '78%'],
            center:
              size.w > 0
                ? [centerX, centerY]
                : showLegend
                  ? ['32%', '50%']
                  : ['50%', '50%'],
            avoidLabelOverlap: false,
            label: { show: false },
            emphasis: {
              label: { show: false },
              scaleSize: 3
            },
            labelLine: { show: false },
            data: finalPieData,
            color: colors.series
          }
        ]
      }
    };
  }, [rawData, config, colors, size]);

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

  const centerDisplayValue = formatDonutCenterValue(total);
  const centerFontScale =
    centerDisplayValue.length >= 7
      ? 0.28
      : centerDisplayValue.length >= 5
        ? 0.32
        : 0.38;

  return (
    <div ref={containerRef} className="relative h-full w-full">
      <ReactEcharts
        option={chartOption}
        style={{ height: '100%', width: '100%' }}
        opts={{ renderer: 'canvas' }}
        notMerge
      />
      {/* 中心汇总数字，跟随 center 坐标 */}
      {size.w > 0 && (
        <div
          className="absolute pointer-events-none flex flex-col items-center justify-center"
          style={{
            left: chartOption.series[0].center[0],
            top: chartOption.series[0].center[1],
            transform: 'translate(-50%, -50%)'
          }}
        >
          <span
            className="font-bold leading-none"
            style={{
              color: colors.textPrimary,
              fontSize: Math.max(
                11,
                Math.floor(
                  (chartOption.series[0].radius[1] as number) * centerFontScale
                )
              )
            }}
          >
            {centerDisplayValue}
          </span>
          <span
            className="text-[10px] mt-0.5"
            style={{ color: colors.textTertiary }}
          >
            总数
          </span>
        </div>
      )}
    </div>
  );
};

export default DockerDonutChart;

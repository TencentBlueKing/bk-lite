import React, { useEffect, useMemo, useRef, useState } from 'react';
import ReactEcharts from 'echarts-for-react';
import ChartSurface from '@/components/chart-surface';
import useChartColors from '@/hooks/useChartColors';

const trimTrailingZeros = (value: string) =>
  value.replace(/\.0+$|(?<=\.\d*[1-9])0+$/g, '');

const getDisplayName = (value: unknown, fallback: string) => {
  const text = String(value ?? '').trim();
  return text || fallback;
};

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

const formatLegendValue = (value: number): string => {
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

const formatTooltipValue = (value: unknown): string | number => {
  try {
    if (value === null || value === undefined || value === '') {
      return '--';
    }

    if (typeof value === 'number') {
      if (isFinite(value)) {
        return Number(value.toFixed(2));
      }
      return value;
    }

    if (typeof value === 'string') {
      const trimmedValue = value.trim();
      if (trimmedValue === '') {
        return value;
      }

      const numValue = Number(trimmedValue);
      if (!isNaN(numValue) && isFinite(numValue)) {
        return Number(numValue.toFixed(2));
      }
    }

    return String(value);
  } catch {
    return String(value);
  }
};

export interface LogDonutChartProps {
  rawData: any;
  loading?: boolean;
  config?: any;
}

const LogDonutChart: React.FC<LogDonutChartProps> = ({
  rawData,
  loading = false,
  config,
}) => {
  const colors = useChartColors();
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const obs = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setSize({
          w: entry.contentRect.width,
          h: entry.contentRect.height,
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
    const fallbackName = displayMaps.emptyLabel || 'Unknown';

    const pieData = rawData.map((item: any) => ({
      name: getDisplayName(item[nameField], fallbackName),
      value: parseFloat(item[valueField]) || 0,
    }));
    const visiblePieData = pieData.filter((item: any) => item.value > 0);
    const finalPieData = visiblePieData.length > 0 ? visiblePieData : pieData;

    const totalVal = finalPieData.reduce(
      (sum: number, d: any) => sum + d.value,
      0
    );
    const showLegend = finalPieData.length >= 1;

    const legendWidth = showLegend ? 176 : 0;
    const chartAreaW = size.w > 0 ? size.w - legendWidth : 200;
    const chartAreaH = size.h > 0 ? size.h - 16 : 180;
    const minSide = Math.min(chartAreaW, chartAreaH);
    const outerR = Math.max(30, Math.floor(minSide * 0.42));
    const innerR = Math.max(18, Math.floor(outerR * 0.68));

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
            return `${params.marker} ${params.name}: ${formatTooltipValue(params.value)} (${params.percent}%)`;
          },
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
            width: 160,
            formatter: (name: string) => {
              const item = finalPieData.find((d: any) => d.name === name);
              if (!item) return name;
              const pct =
                totalVal > 0
                  ? ((item.value / totalVal) * 100).toFixed(1)
                  : '0.0';
              return `${name}  ${pct}% (${formatLegendValue(item.value)})`;
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
                return `${params.name}: ${formatLegendValue(item.value)} (${pct}%)`;
              },
            },
          }
          : { show: false },
        series: [
          {
            type: 'pie',
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
              scaleSize: 3,
            },
            labelLine: { show: false },
            data: finalPieData,
            color: colors.series,
          },
        ],
      },
    };
  }, [rawData, config, colors, size]);

  const centerDisplayValue = formatDonutCenterValue(total);
  const centerFontScale =
    centerDisplayValue.length >= 7
      ? 0.28
      : centerDisplayValue.length >= 5
        ? 0.32
        : 0.38;

  return (
    <ChartSurface
      loading={loading}
      hasData={!!chartOption}
      containerClassName="h-full w-full"
      loadingClassName="flex h-full w-full items-center justify-center"
      emptyClassName="h-full w-full"
      loadingContent={
        <div
          className="h-5 w-5 animate-spin rounded-full border-2 border-t-transparent"
          style={{
            borderColor: `${colors.primary}33`,
            borderTopColor: 'transparent',
          }}
        />
      }
    >
      <div ref={containerRef} className="relative h-full w-full">
        <ReactEcharts
          option={chartOption!}
          style={{ height: '100%', width: '100%' }}
          opts={{ renderer: 'canvas' }}
          notMerge
        />
        {size.w > 0 && (
          <div
            className="absolute pointer-events-none flex flex-col items-center justify-center"
            style={{
              left: chartOption!.series[0].center[0],
              top: chartOption!.series[0].center[1],
              transform: 'translate(-50%, -50%)',
            }}
          >
            <span
              className="font-bold leading-none"
              style={{
                color: colors.textPrimary,
                fontSize: Math.max(
                  11,
                  Math.floor(
                    (chartOption!.series[0].radius[1] as number) * centerFontScale
                  )
                ),
              }}
            >
              {centerDisplayValue}
            </span>
            <span
              className="mt-0.5 text-[10px]"
              style={{ color: colors.textTertiary }}
            >
              总数
            </span>
          </div>
        )}
      </div>
    </ChartSurface>
  );
};

export default LogDonutChart;

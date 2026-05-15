import React, { useMemo, useRef } from 'react';
import ReactEcharts from 'echarts-for-react';
import { Empty } from 'antd';
import useChartColors from './useChartColors';

const trimTrailingZeros = (value: string) =>
  value.replace(/\.0+$|(?<=\.\d*[1-9])0+$/g, '');

const formatRawKpiValue = (value: number): string => {
  if (Number.isInteger(value)) return String(value);
  return trimTrailingZeros(value.toFixed(1));
};

const formatCompactKpiValue = (value: number, unit: 'k' | 'M'): string => {
  const absValue = Math.abs(value);
  const scaledValue = unit === 'M' ? value / 1_000_000 : value / 1_000;
  const scaledIntegerDigits = Math.trunc(Math.abs(scaledValue)).toString()
    .length;
  const decimals = scaledIntegerDigits >= 5 ? 0 : 1;

  if (absValue % (unit === 'M' ? 1_000_000 : 1_000) === 0) {
    return `${scaledValue.toFixed(0)}${unit}`;
  }

  return `${trimTrailingZeros(scaledValue.toFixed(decimals))}${unit}`;
};

/**
 * KPI 数字展示策略：
 * - 小于 1000 不缩写
 * - 整数位不超过 5 时不缩写，小数最多保留 1 位
 * - 其余再按 k / M 缩写
 */
const formatKpiValue = (value: number): string => {
  if (!isFinite(value)) return '--';
  const absValue = Math.abs(value);
  const integerDigitCount = Math.trunc(absValue).toString().length;

  if (absValue < 1_000 || integerDigitCount <= 5) {
    return formatRawKpiValue(value);
  }
  if (absValue >= 1_000_000) {
    return formatCompactKpiValue(value, 'M');
  }
  if (absValue >= 1_000) {
    return formatCompactKpiValue(value, 'k');
  }
  return formatRawKpiValue(value);
};

interface DockerKpiCardProps {
  rawData: any;
  prevData?: any;
  loading?: boolean;
  config?: any;
}

const DockerKpiCard: React.FC<DockerKpiCardProps> = ({
  rawData,
  prevData,
  loading = false,
  config
}) => {
  const colors = useChartColors();
  const containerRef = useRef<HTMLDivElement>(null);

  const accentColor = config?.color || colors.primary;

  const { currentValue, changePercent, trendData } = useMemo(() => {
    const field = config?.displayMaps?.value;
    if (!field || !Array.isArray(rawData) || rawData.length === 0) {
      return { currentValue: undefined, changePercent: null, trendData: [] };
    }

    const values = rawData.map((item: any) => {
      const v = parseFloat(item[field]);
      return isNaN(v) ? 0 : v;
    });

    const total = values.reduce((sum: number, v: number) => sum + v, 0);

    // 计算环比：用上一周期数据总和对比
    let pct: number | null = null;
    if (Array.isArray(prevData) && prevData.length > 0) {
      const prevValues = prevData.map((item: any) => {
        const v = parseFloat(item[field]);
        return isNaN(v) ? 0 : v;
      });
      const prevTotal = prevValues.reduce(
        (sum: number, v: number) => sum + v,
        0
      );
      if (prevTotal !== 0) {
        pct = ((total - prevTotal) / prevTotal) * 100;
      } else if (total > 0) {
        pct = 100;
      }
    }

    return { currentValue: total, changePercent: pct, trendData: values };
  }, [rawData, prevData, config]);

  const sparklineOption = {
    animation: false,
    grid: { top: 2, right: 0, bottom: 2, left: 0 },
    xAxis: {
      type: 'category' as const,
      show: false,
      data: trendData.map((_, i) => i)
    },
    yAxis: { type: 'value' as const, show: false },
    series: [
      {
        type: 'line' as const,
        data: trendData,
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 1.5, color: accentColor },
        areaStyle: {
          opacity: 0.15,
          color: accentColor
        }
      }
    ]
  };

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div
          className="w-5 h-5 rounded-full border-2 border-t-transparent animate-spin"
          style={{
            borderColor: `${accentColor}33`,
            borderTopColor: 'transparent'
          }}
        />
      </div>
    );
  }

  if (currentValue === undefined) {
    return (
      <div className="h-full flex items-center justify-center">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </div>
    );
  }

  const isUp = changePercent !== null && changePercent > 0;
  const isDown = changePercent !== null && changePercent < 0;

  // 副标题已移至卡片层（index.tsx），组件内不再渲染
  // const subLabel = config?.description || config?.metricLabel || '';

  return (
    <div ref={containerRef} className="flex h-full w-full overflow-hidden">
      {/* 左侧：文字区，无额外 padding（外层卡片已有 px-4 pb-4 pt-3） */}
      <div className="flex flex-col justify-center min-w-0 flex-1">
        {/* 数值：自适应字号防超长溢出 */}
        <div
          className="font-bold leading-none min-w-0"
          style={{
            color: accentColor,
            fontSize: 'clamp(1.1rem, 2.5vw, 1.75rem)'
          }}
        >
          {formatKpiValue(currentValue)}
        </div>
        {/* 环比，与数字保持 10px 间距 */}
        <div className="flex items-center gap-1 text-xs flex-wrap mt-[10px]">
          <span style={{ color: 'var(--color-text-3)' }}>较上一周期</span>
          {changePercent !== null ? (
            <span
              className="font-medium"
              style={{
                color: isUp
                  ? colors.danger
                  : isDown
                    ? colors.success
                    : colors.textTertiary
              }}
            >
              {isUp ? '↑' : isDown ? '↓' : ''}
              {Math.abs(changePercent).toFixed(1)}%
            </span>
          ) : (
            <span style={{ color: colors.textTertiary }}>--</span>
          )}
        </div>
      </div>

      {/* 右侧：sparkline，无额外 padding */}
      <div className="flex-shrink-0 w-[45%] min-h-0">
        {trendData.length > 1 ? (
          <ReactEcharts
            option={sparklineOption}
            style={{ height: '100%', width: '100%' }}
            opts={{ renderer: 'svg' }}
          />
        ) : (
          <div className="h-full" />
        )}
      </div>
    </div>
  );
};

export default DockerKpiCard;

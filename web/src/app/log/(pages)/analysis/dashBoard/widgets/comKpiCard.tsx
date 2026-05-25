import React, { useLayoutEffect, useMemo, useRef, useState } from 'react';
import ReactEcharts from 'echarts-for-react';
import { Empty } from 'antd';
import useChartColors, { type ChartColors } from './docker/useChartColors';

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

export const formatKpiValue = (value: number): string => {
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

const MAX_SPARKLINE_POINTS = 24;

export const limitSparklinePoints = (
  values: number[],
  maxPoints = MAX_SPARKLINE_POINTS
) => {
  if (values.length <= maxPoints) return values;
  if (maxPoints <= 2) return [values[0], values[values.length - 1]];

  const lastIndex = values.length - 1;
  const middleCount = maxPoints - 2;
  const step = lastIndex / (middleCount + 1);
  const sampled = [values[0]];

  for (let i = 1; i <= middleCount; i += 1) {
    sampled.push(values[Math.round(step * i)]);
  }

  sampled.push(values[lastIndex]);
  return sampled;
};

const getBaseFontSizeByWidth = (width: number) => {
  const safeWidth = Math.max(width, 120);
  return Math.max(28, Math.min(40, safeWidth / 4.25));
};

const MIN_VALUE_FONT_SIZE = 18;
const UNIT_FONT_SCALE = 0.54;

const splitValueAndUnit = (value: string) => {
  const normalizedValue = value.trim();
  const match = normalizedValue.match(/^([+-]?(?:\d+(?:\.\d+)?|\.\d+))(.*)$/);

  if (!match) {
    return { main: normalizedValue || '--', unit: '' };
  }

  return {
    main: match[1],
    unit: match[2].trim()
  };
};

const toNumber = (value: unknown) => {
  const parsed = Number.parseFloat(String(value ?? 0));
  return Number.isNaN(parsed) ? 0 : parsed;
};

const resolveAccentColor = (colorKey: unknown, colors: ChartColors) => {
  switch (colorKey) {
    case 'primary':
      return colors.primary;
    case 'success':
      return colors.success;
    case 'warning':
      return colors.warning;
    case 'danger':
      return colors.danger;
    case 'info':
      return colors.series[1] || colors.primary;
    case 'accent':
      return colors.series[5] || colors.primary;
    default:
      return typeof colorKey === 'string' && colorKey
        ? colorKey
        : colors.primary;
  }
};

interface MetricResult {
  currentValue: number | undefined;
  changePercent: number | null;
  trendData: number[];
}

interface SharedKpiCardProps {
  rawData: any;
  prevData?: any;
  loading?: boolean;
  config?: any;
  calculateMetric?: (rawData: any, prevData: any, config: any) => MetricResult;
}

const defaultCalculateMetric = (
  rawData: any,
  prevData: any,
  config: any
): MetricResult => {
  const field = config?.displayMaps?.value;
  if (!field || !Array.isArray(rawData) || rawData.length === 0) {
    return { currentValue: undefined, changePercent: null, trendData: [] };
  }

  const values = rawData.map((item: any) => toNumber(item[field]));
  const total = values.reduce((sum: number, value: number) => sum + value, 0);
  let pct: number | null = null;

  if (Array.isArray(prevData) && prevData.length > 0) {
    const prevValues = prevData.map((item: any) => toNumber(item[field]));
    const prevTotal = prevValues.reduce(
      (sum: number, value: number) => sum + value,
      0
    );
    if (prevTotal !== 0) {
      pct = ((total - prevTotal) / prevTotal) * 100;
    } else if (total > 0) {
      pct = 100;
    }
  } else if (values.length > 1) {
    const lastVal = values[values.length - 1];
    const prevVal = values[values.length - 2];
    if (prevVal !== 0) {
      pct = ((lastVal - prevVal) / prevVal) * 100;
    }
  }

  return {
    currentValue: total,
    changePercent: pct,
    trendData: values.length > 1 ? values : []
  };
};

const ComKpiCard: React.FC<SharedKpiCardProps> = ({
  rawData,
  prevData,
  loading = false,
  config,
  calculateMetric
}) => {
  const colors = useChartColors();
  const valueAreaRef = useRef<HTMLDivElement>(null);
  const measureRef = useRef<HTMLDivElement>(null);
  const [valueFontSize, setValueFontSize] = useState(36);
  const accentColor = resolveAccentColor(config?.color, colors);

  const metricResult = useMemo(
    () =>
      (calculateMetric || defaultCalculateMetric)(rawData, prevData, config),
    [calculateMetric, config, prevData, rawData]
  );

  const sparklineData = useMemo(
    () => limitSparklinePoints(metricResult.trendData),
    [metricResult.trendData]
  );

  const displayValue =
    metricResult.currentValue === undefined
      ? '--'
      : config?.valueFormatter
        ? config.valueFormatter(metricResult.currentValue)
        : formatKpiValue(metricResult.currentValue);

  const { main: displayMainValue, unit: displayUnit } = useMemo(
    () => splitValueAndUnit(displayValue),
    [displayValue]
  );

  useLayoutEffect(() => {
    const valueArea = valueAreaRef.current;
    const measureElement = measureRef.current;
    if (!valueArea || !measureElement) {
      return;
    }

    let frameId = 0;

    const updateFontSize = () => {
      const availableWidth = valueArea.clientWidth;
      if (availableWidth <= 0) return;

      let nextFontSize = getBaseFontSizeByWidth(availableWidth);
      measureElement.style.fontSize = `${nextFontSize}px`;

      while (
        nextFontSize > MIN_VALUE_FONT_SIZE &&
        measureElement.scrollWidth > availableWidth
      ) {
        nextFontSize -= 0.5;
        measureElement.style.fontSize = `${nextFontSize}px`;
      }

      setValueFontSize((prev) =>
        Math.abs(prev - nextFontSize) < 0.1 ? prev : nextFontSize
      );
    };

    updateFontSize();

    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frameId);
      frameId = requestAnimationFrame(updateFontSize);
    });

    observer.observe(valueArea);

    return () => {
      cancelAnimationFrame(frameId);
      observer.disconnect();
    };
  }, [displayMainValue, displayUnit]);

  const valueGap = displayUnit
    ? Math.max(4, Math.round(valueFontSize * 0.08))
    : 0;

  const sparklineOption = {
    animation: false,
    grid: { top: 2, right: 0, bottom: 2, left: 0 },
    xAxis: {
      type: 'category' as const,
      show: false,
      data: sparklineData.map((_, i) => i)
    },
    yAxis: { type: 'value' as const, show: false },
    series: [
      {
        type: 'line' as const,
        data: sparklineData,
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

  if (metricResult.currentValue === undefined) {
    return (
      <div className="h-full flex items-center justify-center">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </div>
    );
  }

  const isUp =
    metricResult.changePercent !== null && metricResult.changePercent > 0;
  const isDown =
    metricResult.changePercent !== null && metricResult.changePercent < 0;

  return (
    <div className="flex h-full w-full items-center gap-3 overflow-hidden">
      <div
        className="flex min-w-0 flex-col justify-center"
        style={{
          flex: '0 1 46%',
          minWidth: '100px',
          maxWidth: '46%'
        }}
      >
        <div ref={valueAreaRef} className="relative min-w-0">
          <div
            className="inline-flex max-w-full items-end whitespace-nowrap font-bold leading-none"
            style={{
              color: accentColor,
              fontSize: `${valueFontSize}px`,
              gap: `${valueGap}px`
            }}
          >
            <span>{displayMainValue}</span>
            {displayUnit ? (
              <span
                className="shrink-0 font-semibold leading-none"
                style={{ fontSize: `${UNIT_FONT_SCALE}em` }}
              >
                {displayUnit}
              </span>
            ) : null}
          </div>
          <div
            ref={measureRef}
            className="pointer-events-none absolute left-0 top-0 inline-flex items-end whitespace-nowrap font-bold leading-none opacity-0"
            aria-hidden
            style={{ gap: `${valueGap}px` }}
          >
            <span>{displayMainValue}</span>
            {displayUnit ? (
              <span
                className="shrink-0 font-semibold leading-none"
                style={{ fontSize: `${UNIT_FONT_SCALE}em` }}
              >
                {displayUnit}
              </span>
            ) : null}
          </div>
        </div>
        <div className="flex items-center gap-1 text-xs flex-wrap mt-[10px]">
          <span style={{ color: colors.textTertiary }}>较上一周期</span>
          {metricResult.changePercent !== null ? (
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
              {Math.abs(metricResult.changePercent).toFixed(1)}%
            </span>
          ) : (
            <span style={{ color: colors.textTertiary }}>--</span>
          )}
        </div>
      </div>

      <div className="min-h-0 min-w-[72px] flex-[1_1_54%]">
        {sparklineData.length > 1 ? (
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

export default ComKpiCard;

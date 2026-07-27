import React, { useMemo, useState } from 'react';
import ReactEcharts from 'echarts-for-react';
import AutoFitMetricValue from '@/components/auto-fit-metric-value';
import ChartSurface from '@/components/chart-surface';
import useChartColors, {
  type ChartColors,
} from '@/hooks/useChartColors';

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

export interface LogKpiCardMetricResult {
  currentValue: number | undefined;
  changePercent: number | null;
  trendData: number[];
}

export type LogKpiCardCalculateMetric = (
  rawData: any,
  prevData: any,
  config: any
) => LogKpiCardMetricResult;

export interface LogKpiCardProps {
  rawData: any;
  prevData?: any;
  loading?: boolean;
  config?: any;
  calculateMetric?: LogKpiCardCalculateMetric;
}

const defaultCalculateMetric = (
  rawData: any,
  prevData: any,
  config: any
): LogKpiCardMetricResult => {
  const field = config?.displayMaps?.value;
  if (!field || !Array.isArray(rawData) || rawData.length === 0) {
    return { currentValue: undefined, changePercent: null, trendData: [] };
  }

  const values = rawData.map((item: any) => toNumber(item[field]));
  const metricMode = config?.metricMode === 'latest' ? 'latest' : 'sum';
  const total = values.reduce((sum: number, value: number) => sum + value, 0);
  const currentValue =
    metricMode === 'latest' ? values[values.length - 1] ?? 0 : total;
  let pct: number | null = null;

  if (Array.isArray(prevData) && prevData.length > 0) {
    const prevValues = prevData.map((item: any) => toNumber(item[field]));
    const prevTotal = prevValues.reduce(
      (sum: number, value: number) => sum + value,
      0
    );
    const prevValue =
      metricMode === 'latest'
        ? prevValues[prevValues.length - 1] ?? 0
        : prevTotal;
    if (prevValue !== 0) {
      pct = ((currentValue - prevValue) / prevValue) * 100;
    } else if (currentValue > 0) {
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
    currentValue,
    changePercent: pct,
    trendData: values.length > 1 ? values : []
  };
};

const LogKpiCard: React.FC<LogKpiCardProps> = ({
  rawData,
  prevData,
  loading = false,
  config,
  calculateMetric
}) => {
  const colors = useChartColors();
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

  const isUp =
    metricResult.changePercent !== null && metricResult.changePercent > 0;
  const isDown =
    metricResult.changePercent !== null && metricResult.changePercent < 0;

  return (
    <ChartSurface
      loading={loading}
      hasData={metricResult.currentValue !== undefined}
      containerClassName="h-full w-full"
      loadingClassName="flex h-full w-full items-center justify-center"
      emptyClassName="h-full w-full"
      loadingContent={
        <div
          className="h-5 w-5 animate-spin rounded-full border-2 border-t-transparent"
          style={{
            borderColor: `${accentColor}33`,
            borderTopColor: 'transparent',
          }}
        />
      }
    >
      <div className="flex h-full w-full items-center gap-3 overflow-hidden">
        <div
          className="flex min-w-0 flex-col justify-center"
          style={{
            flex: '0 1 46%',
            minWidth: '100px',
            maxWidth: '46%'
          }}
        >
          <AutoFitMetricValue
            main={displayMainValue}
            unit={displayUnit || undefined}
            color={accentColor}
            align="end"
            valueClassName="font-bold"
            unitClassName="font-semibold"
            gap={valueGap}
            unitScale={UNIT_FONT_SCALE}
            resolveFontSize={({ width }) => getBaseFontSizeByWidth(width)}
            onFontSizeChange={setValueFontSize}
          />
          <div className="mt-[10px] flex flex-wrap items-center gap-1 text-xs">
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
    </ChartSurface>
  );
};

export default LogKpiCard;

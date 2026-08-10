import React, {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import ReactEcharts from 'echarts-for-react';
import { Spin } from 'antd';
import {
  getColorByThreshold,
  formatDisplayValue,
  ThresholdColorConfig,
} from '@/app/ops-analysis/utils/thresholdUtils';
import { applyValueMapping } from '@/app/ops-analysis/utils/valueMapping';
import { DEFAULT_THRESHOLD_COLORS } from '@/app/ops-analysis/constants/threshold';
import {
  ScreenRenderContext,
  ValueConfig,
} from '@/app/ops-analysis/types/dashBoard';
import {
  getOpsChartThemeByMode,
  isScreenChartThemeMode,
} from '@/app/ops-analysis/utils/chartTheme';
import {
  extractComparableValue,
  getChangePercent,
  toComparableNumber,
} from '@/app/ops-analysis/utils/compareQuery';
import { getValueByPath } from '@/app/ops-analysis/utils/objectPath';
import { buildFallbackSparkline } from '@/app/ops-analysis/utils/singleValueSparkline';
import { useTranslation } from '@/utils/i18n';
import OpsAnalysisMetricValue from '@/app/ops-analysis/components/ops-analysis-metric-value';
import WidgetState from '@/app/ops-analysis/components/widget-state';
import {
  scaleScreenMetric,
  scaleScreenMetricFloat,
} from './shared/screenMetrics';

const MAX_SPARKLINE_POINTS = 24;
const UNIT_FONT_SCALE = 0.48;
const COMPARE_METRIC_HEIGHT_FILL_RATIO = 0.7;

const toAlphaColor = (color: string, alpha: number) => {
  const normalized = color.trim();

  if (normalized.startsWith('#')) {
    let hex = normalized.slice(1);
    if (hex.length === 3) {
      hex = hex
        .split('')
        .map((char) => char + char)
        .join('');
    }
    if (hex.length !== 6) {
      return color;
    }

    const red = parseInt(hex.slice(0, 2), 16);
    const green = parseInt(hex.slice(2, 4), 16);
    const blue = parseInt(hex.slice(4, 6), 16);
    return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
  }

  const rgbMatch = normalized.match(/^rgba?\(([^)]+)\)$/i);
  if (!rgbMatch) {
    return color;
  }

  const [red = '0', green = '0', blue = '0'] = rgbMatch[1]
    .split(',')
    .map((part) => part.trim());
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
};

const limitSparklinePoints = (
  values: number[],
  maxPoints = MAX_SPARKLINE_POINTS,
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

const splitValueAndUnit = (value: string) => {
  const normalizedValue = value.trim();
  const match = normalizedValue.match(
    /^([+-]?(?:(?:\d{1,3}(?:,\d{3})+)|\d+)(?:\.\d+)?|[+-]?\.\d+)(.*)$/,
  );

  if (!match) {
    return { main: normalizedValue || '--', unit: '' };
  }

  return {
    main: match[1],
    unit: match[2].trim(),
  };
};

const formatWithThousands = (value: string | number | null): string => {
  if (value === null) return '--';
  const strVal = String(value);
  const parts = strVal.split('.');
  const intPart = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return parts.length > 1 ? `${intPart}.${parts[1]}` : intPart;
};

const extractSparklineValues = (
  data: unknown,
  selectedField?: string,
): number[] => {
  if (!Array.isArray(data) || data.length < 2) {
    return [];
  }

  const values = data
    .map((item) => {
      if (selectedField) {
        const selectedValue = getValueByPath(item, selectedField);
        if (
          typeof selectedValue === 'number' ||
          typeof selectedValue === 'string'
        ) {
          return toComparableNumber(selectedValue);
        }
      }

      if (typeof item === 'number' || typeof item === 'string') {
        return toComparableNumber(item);
      }

      return toComparableNumber(extractComparableValue(item, selectedField));
    })
    .filter(
      (value): value is number => value !== null && Number.isFinite(value),
    );

  return values.length > 1 ? limitSparklinePoints(values) : [];
};

interface ComSingleProps {
  rawData: unknown;
  baselineData?: unknown;
  loading?: boolean;
  config?: ValueConfig;
  screenRenderContext?: ScreenRenderContext;
  onReady?: (ready: boolean) => void;
}

const ComSingle: React.FC<ComSingleProps> = ({
  rawData,
  baselineData,
  loading = false,
  config,
  screenRenderContext,
  onReady,
}) => {
  const { t } = useTranslation();
  const chartTheme = getOpsChartThemeByMode(config?.chartThemeMode);
  const usesScreenTheme = isScreenChartThemeMode(config?.chartThemeMode);
  const contentAreaRef = useRef<HTMLDivElement>(null);
  const [compareSpacing, setCompareSpacing] = useState(10);
  const [contentAreaHeight, setContentAreaHeight] = useState(0);

  const selectedField = config?.selectedFields?.[0];
  const rawValue = extractComparableValue(rawData, selectedField);
  const baselineRawValue = extractComparableValue(baselineData, selectedField);
  const numericValue =
    rawValue !== null
      ? typeof rawValue === 'string'
        ? parseFloat(rawValue)
        : rawValue
      : null;
  const baselineNumericValue = toComparableNumber(baselineRawValue);
  const changePercent = config?.compare
    ? getChangePercent(toComparableNumber(rawValue), baselineNumericValue)
    : null;
  const currentNumericValue = toComparableNumber(rawValue);
  const changeValue = config?.compare && currentNumericValue !== null && baselineNumericValue !== null
    ? currentNumericValue - baselineNumericValue
    : null;

  const thresholds: ThresholdColorConfig[] =
    config?.thresholdColors ?? DEFAULT_THRESHOLD_COLORS;
  const color = getColorByThreshold(numericValue, thresholds, '#000000');
  const isDataReady = rawValue !== null;
  const displayValue = formatDisplayValue(
    numericValue,
    undefined,
    config?.decimalPlaces,
    config?.conversionFactor,
    config?.unitId,
  );
  const unitText = config?.unit?.trim() || '';
  const fallbackSparklineSeed = useMemo(
    () =>
      JSON.stringify([
        config?.dataSource,
        selectedField,
        rawValue,
        baselineRawValue,
        unitText,
      ]),
    [baselineRawValue, config?.dataSource, rawValue, selectedField, unitText],
  );
  const sourceSparklineData = useMemo(
    () => extractSparklineValues(rawData, selectedField),
    [rawData, selectedField],
  );
  const sparklineData = useMemo(
    () =>
      sourceSparklineData.length > 1
        ? sourceSparklineData
        : buildFallbackSparkline(
          numericValue,
          baselineNumericValue,
          fallbackSparklineSeed,
        ),
    [
      baselineNumericValue,
      fallbackSparklineSeed,
      numericValue,
      sourceSparklineData,
    ],
  );
  const showSparkline = Boolean(config?.compare) && sparklineData.length > 1;
  const displayText = formatWithThousands(displayValue);
  const { main: displayMainValue, unit: displayUnit } = useMemo(
    () => splitValueAndUnit(displayText),
    [displayText],
  );

  useEffect(() => {
    if (!loading) {
      onReady?.(isDataReady);
    }
  }, [isDataReady, loading, onReady]);

  useLayoutEffect(() => {
    const contentArea = contentAreaRef.current;
    if (!contentArea) {
      return;
    }

    let frameId = 0;

    const updateCompareSpacing = () => {
      setContentAreaHeight((prev) =>
        prev === contentArea.clientHeight ? prev : contentArea.clientHeight,
      );
      const nextSpacing = Math.max(
        scaleScreenMetric(10, screenRenderContext),
        Math.min(
          scaleScreenMetric(24, screenRenderContext),
          Math.round(contentArea.clientHeight * 0.1),
        ),
      );
      setCompareSpacing((prev) => (prev === nextSpacing ? prev : nextSpacing));
    };

    updateCompareSpacing();

    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frameId);
      frameId = requestAnimationFrame(updateCompareSpacing);
    });

    observer.observe(contentArea);

    return () => {
      cancelAnimationFrame(frameId);
      observer.disconnect();
    };
  }, [screenRenderContext, showSparkline]);

  // 值映射：命中时覆盖展示文本与颜色（优先于数值/阈值色）
  const valueMappingResult = applyValueMapping(rawValue, config?.valueMappings);
  const metricColor =
    valueMappingResult?.color || color || chartTheme.singleValueColor;
  const compareUnitLabel =
    valueMappingResult?.text !== undefined ? '' : displayUnit || unitText;
  const compareAmount = config?.compareMode === 'value' ? changeValue : changePercent;
  const compareTextColor =
    compareAmount === null
      ? chartTheme.singleValueMetaColor
      : compareAmount > 0
        ? '#ff4d4f'
        : compareAmount < 0
          ? '#52c41a'
          : chartTheme.singleValueMetaColor;
  const compareDisplayText =
    compareAmount === null
      ? '--'
      : `${compareAmount > 0 ? '↑' : compareAmount < 0 ? '↓' : ''}${Math.abs(compareAmount).toFixed(config?.compareMode === 'value' ? (config.decimalPlaces ?? 0) : 1)}${config?.compareMode === 'value' ? compareUnitLabel : '%'}`;
  const heightDrivenCompareSize = Math.round(Math.max(contentAreaHeight, 0) * 0.1);
  const compareLabelFontSize = Math.max(
    scaleScreenMetric(11, screenRenderContext),
    Math.min(
      scaleScreenMetric(16, screenRenderContext),
      heightDrivenCompareSize - 3,
    ),
  );
  const compareValueFontSize = Math.max(
    scaleScreenMetric(13, screenRenderContext),
    Math.min(scaleScreenMetric(22, screenRenderContext), heightDrivenCompareSize),
  );
  const sparklineTrendColor = config?.compare ? compareTextColor : metricColor;
  // 命中值映射文本时，用映射文本替换数值并隐藏单位
  const shownMainValue =
    valueMappingResult?.text !== undefined
      ? valueMappingResult.text
      : displayMainValue;
  const unitLabel = compareUnitLabel;
  const sparklineLineColor = {
    type: 'linear' as const,
    x: 0,
    y: 0,
    x2: 1,
    y2: 0,
    colorStops: [
      { offset: 0, color: toAlphaColor(sparklineTrendColor, 0.05) },
      { offset: 0.18, color: toAlphaColor(sparklineTrendColor, 0.46) },
      { offset: 0.82, color: toAlphaColor(sparklineTrendColor, 0.46) },
      { offset: 1, color: toAlphaColor(sparklineTrendColor, 0.05) },
    ],
  };
  const sparklineAreaColor = {
    type: 'linear' as const,
    x: 0,
    y: 0,
    x2: 0,
    y2: 1,
    colorStops: [
      { offset: 0, color: toAlphaColor(sparklineTrendColor, 0.2) },
      { offset: 0.55, color: toAlphaColor(sparklineTrendColor, 0.08) },
      { offset: 1, color: toAlphaColor(sparklineTrendColor, 0) },
    ],
  };
  const sparklineOption = useMemo(
    () => ({
      animation: false,
      grid: { top: scaleScreenMetric(12, screenRenderContext), right: 0, bottom: 0, left: 0 },
      xAxis: {
        type: 'category' as const,
        show: false,
        data: sparklineData.map((_, index) => index),
      },
      yAxis: {
        type: 'value' as const,
        show: false,
        scale: true,
      },
      series: [
        {
          type: 'line' as const,
          data: sparklineData,
          smooth: true,
          symbol: 'none',
          lineStyle: {
            width: scaleScreenMetricFloat(1.1, screenRenderContext),
            color: sparklineLineColor,
          },
          areaStyle: {
            color: sparklineAreaColor,
          },
        },
      ],
    }),
    [screenRenderContext, sparklineAreaColor, sparklineData, sparklineLineColor],
  );

  if (loading) {
    return (
      <div className="h-full flex flex-col items-center justify-center">
        <Spin size="small" />
      </div>
    );
  }

  // 命中值映射文本（如 null→"无数据"）时仍正常展示，不走空态
  if (
    (!isDataReady || rawValue === null) &&
    valueMappingResult?.text === undefined
  ) {
    return <WidgetState />;
  }

  return (
    <div
      className={`flex h-full w-full flex-col overflow-hidden ${
        usesScreenTheme ? '' : 'px-2'
      }`}
    >
      <div
        ref={contentAreaRef}
        className="flex min-h-0 flex-1 flex-col justify-center"
      >
        <div className="min-h-0 w-full flex-1">
          <OpsAnalysisMetricValue
            main={shownMainValue}
            unit={unitLabel || undefined}
            color={metricColor}
            unitColor={toAlphaColor(metricColor, 0.78)}
            valueClassName="font-semibold"
            unitClassName="font-medium"
            fontVariantNumeric="tabular-nums"
            textShadow={chartTheme.singleValueGlow}
            unitScale={UNIT_FONT_SCALE}
            unitTransform="translateY(-0.02em)"
            heightFillRatio={
              config?.compare ? COMPARE_METRIC_HEIGHT_FILL_RATIO : undefined
            }
          />
        </div>

        {config?.compare && (
          <div
            className="flex shrink-0 flex-wrap items-center gap-1"
            style={{
              marginTop: compareSpacing,
              color: chartTheme.singleValueMetaColor,
              lineHeight: 1.2,
            }}
          >
            <span
              style={{
                color: chartTheme.singleValueMetaColor,
                fontSize: compareLabelFontSize,
              }}
            >
              {t('dashboard.comparePreviousShortLabel')}
            </span>
            <span
              className="font-semibold"
              style={{
                color: compareTextColor,
                fontSize: compareValueFontSize,
                lineHeight: 1,
              }}
            >
              {compareDisplayText}
            </span>
          </div>
        )}

        {showSparkline ? (
          <div
            className="w-full shrink-0"
            style={{
              height: scaleScreenMetric(28, screenRenderContext),
              marginTop: scaleScreenMetric(6, screenRenderContext),
            }}
          >
            <ReactEcharts
              option={sparklineOption}
              style={{ height: '100%', width: '100%' }}
              opts={{ renderer: 'canvas' }}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
};

export default ComSingle;

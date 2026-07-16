import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import ReactEcharts from 'echarts-for-react';
import AutoFitMetricValue from '@/components/auto-fit-metric-value';
import {
  DEFAULT_THRESHOLD_COLORS,
  applyValueMapping,
  formatDisplayValue,
  getColorByThreshold,
  getValueByPath,
  type ThresholdColorConfig,
} from '@/components/ops-analysis-config-sections';
import {
  buildFallbackSparkline,
  extractComparableValue,
  getChangePercent,
  getOpsChartTheme,
  resolveOpsChartThemeName,
  toComparableNumber,
} from '@/components/ops-analysis-widgets/runtime';
import type { ValueConfig } from '@/components/ops-analysis-widgets';
import ChartSurface from '@/components/chart-surface';
import { useTranslation } from '@/utils/i18n';

const MAX_SPARKLINE_POINTS = 24;
const MIN_VALUE_FONT_SIZE = 18;
const UNIT_FONT_SCALE = 0.48;
const MIN_UNIT_GAP = 8;
const MAX_UNIT_GAP = 12;

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

  const [red = '0', green = '0', blue = '0'] = rgbMatch[1].split(',').map((part) => part.trim());
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
};

const limitSparklinePoints = (values: number[], maxPoints = MAX_SPARKLINE_POINTS) => {
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
  return Math.max(24, Math.min(52, safeWidth / 4.75));
};

const getBaseFontSizeByHeight = (height: number, hasCompare: boolean) => {
  const safeHeight = Math.max(height, 120);
  return Math.max(MIN_VALUE_FONT_SIZE, Math.min(58, safeHeight * (hasCompare ? 0.29 : 0.36)));
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

const extractSparklineValues = (data: unknown, selectedField?: string): number[] => {
  if (!Array.isArray(data) || data.length < 2) {
    return [];
  }

  const values = data
    .map((item) => {
      if (selectedField) {
        const selectedValue = getValueByPath(item, selectedField);
        if (typeof selectedValue === 'number' || typeof selectedValue === 'string') {
          return toComparableNumber(selectedValue);
        }
      }

      if (typeof item === 'number' || typeof item === 'string') {
        return toComparableNumber(item);
      }

      return toComparableNumber(extractComparableValue(item, selectedField));
    })
    .filter((value): value is number => value !== null && Number.isFinite(value));

  return values.length > 1 ? limitSparklinePoints(values) : [];
};

export interface OpsAnalysisSingleProps {
  rawData: unknown;
  baselineData?: unknown;
  loading?: boolean;
  config?: ValueConfig;
  onReady?: (ready: boolean) => void;
}

const OpsAnalysisSingle: React.FC<OpsAnalysisSingleProps> = ({
  rawData,
  baselineData,
  loading = false,
  config,
  onReady,
}) => {
  const { t } = useTranslation();
  const chartTheme = getOpsChartTheme(resolveOpsChartThemeName());
  const contentAreaRef = useRef<HTMLDivElement>(null);
  const [valueFontSize, setValueFontSize] = useState(36);
  const [compareSpacing, setCompareSpacing] = useState(10);
  const [contentAreaHeight, setContentAreaHeight] = useState(0);

  const selectedField = config?.selectedFields?.[0];
  const rawValue = extractComparableValue(rawData, selectedField);
  const baselineRawValue = extractComparableValue(baselineData, selectedField);
  const numericValue = rawValue !== null ? (typeof rawValue === 'string' ? parseFloat(rawValue) : rawValue) : null;
  const baselineNumericValue = toComparableNumber(baselineRawValue);
  const changePercent = config?.compare ? getChangePercent(toComparableNumber(rawValue), baselineNumericValue) : null;

  const thresholds: ThresholdColorConfig[] = config?.thresholdColors ?? DEFAULT_THRESHOLD_COLORS;
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
    () => JSON.stringify([config?.dataSource, selectedField, rawValue, baselineRawValue, unitText]),
    [baselineRawValue, config?.dataSource, rawValue, selectedField, unitText],
  );
  const sourceSparklineData = useMemo(() => extractSparklineValues(rawData, selectedField), [rawData, selectedField]);
  const sparklineData = useMemo(
    () =>
      sourceSparklineData.length > 1
        ? sourceSparklineData
        : buildFallbackSparkline(numericValue, baselineNumericValue, fallbackSparklineSeed),
    [baselineNumericValue, fallbackSparklineSeed, numericValue, sourceSparklineData],
  );
  const showSparkline = Boolean(config?.compare) && sparklineData.length > 1;
  const displayText = formatWithThousands(displayValue);
  const { main: displayMainValue, unit: displayUnit } = useMemo(() => splitValueAndUnit(displayText), [displayText]);

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

    const updateContentHeight = () => {
      const availableHeight = contentArea.clientHeight;
      if (availableHeight <= 0) return;
      setContentAreaHeight((prev) =>
        Math.abs(prev - availableHeight) < 0.1 ? prev : availableHeight,
      );
    };

    updateContentHeight();

    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frameId);
      frameId = requestAnimationFrame(updateContentHeight);
    });

    observer.observe(contentArea);

    return () => {
      cancelAnimationFrame(frameId);
      observer.disconnect();
    };
  }, [config?.compare, displayMainValue, displayUnit, showSparkline, unitText]);

  useLayoutEffect(() => {
    const contentArea = contentAreaRef.current;
    if (!contentArea) {
      return;
    }

    let frameId = 0;

    const updateCompareSpacing = () => {
      setContentAreaHeight((prev) => (prev === contentArea.clientHeight ? prev : contentArea.clientHeight));
      const nextSpacing = Math.max(10, Math.min(24, Math.round(contentArea.clientHeight * 0.1)));
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
  }, [showSparkline]);

  const valueMappingResult = applyValueMapping(rawValue, config?.valueMappings);
  const metricColor = valueMappingResult?.color || color || chartTheme.singleValueColor;
  const compareTextColor =
    changePercent === null
      ? chartTheme.singleValueMetaColor
      : changePercent > 0
        ? '#ff4d4f'
        : changePercent < 0
          ? '#52c41a'
          : chartTheme.singleValueMetaColor;
  const compareDisplayText =
    changePercent === null
      ? '--'
      : `${changePercent > 0 ? '↑' : changePercent < 0 ? '↓' : ''}${Math.abs(changePercent).toFixed(1)}%`;
  const heightDrivenCompareSize = Math.max(12, Math.min(20, Math.round(contentAreaHeight * 0.1)));
  const compareLabelFontSize = Math.max(
    11,
    Math.min(16, Math.max(Math.round(valueFontSize * 0.27), heightDrivenCompareSize - 3)),
  );
  const compareValueFontSize = Math.max(
    13,
    Math.min(22, Math.max(Math.round(valueFontSize * 0.38), heightDrivenCompareSize)),
  );
  const sparklineTrendColor = config?.compare ? compareTextColor : metricColor;
  const shownMainValue = valueMappingResult?.text !== undefined ? valueMappingResult.text : displayMainValue;
  const unitLabel = valueMappingResult?.text !== undefined ? '' : displayUnit || unitText;
  const valueGap = unitLabel
    ? Math.min(MAX_UNIT_GAP, Math.max(MIN_UNIT_GAP, Math.round(valueFontSize * 0.14)))
    : 0;
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
      grid: { top: 12, right: 0, bottom: 0, left: 0 },
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
            width: 1.1,
            color: sparklineLineColor,
          },
          areaStyle: {
            color: sparklineAreaColor,
          },
        },
      ],
    }),
    [sparklineAreaColor, sparklineData, sparklineLineColor],
  );

  return (
    <ChartSurface
      loading={loading}
      hasData={!!isDataReady || rawValue !== null || valueMappingResult?.text !== undefined}
      containerClassName="flex h-full w-full flex-col overflow-hidden px-2"
      loadingClassName="flex h-full w-full items-center justify-center"
      emptyClassName="flex h-full w-full items-center justify-center"
    >
      <div ref={contentAreaRef} className="flex min-h-0 flex-1 flex-col justify-center">
        <div className="min-w-0">
          <AutoFitMetricValue
            main={shownMainValue}
            unit={unitLabel || undefined}
            color={metricColor}
            unitColor={toAlphaColor(metricColor, 0.78)}
            valueClassName="font-semibold"
            unitClassName="font-medium"
            fontVariantNumeric="tabular-nums"
            gap={valueGap}
            textShadow={chartTheme.singleValueGlow}
            unitScale={UNIT_FONT_SCALE}
            unitTransform="translateY(-0.02em)"
            resolveFontSize={({ width, height }) =>
              Math.min(
                getBaseFontSizeByWidth(width),
                getBaseFontSizeByHeight(height, Boolean(config?.compare)),
              )
            }
            onFontSizeChange={setValueFontSize}
          />

          {config?.compare && (
            <div
              className="flex flex-wrap items-center gap-1"
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
        </div>

        {showSparkline ? (
          <div className="mt-1.5 h-7 w-full shrink-0">
            <ReactEcharts option={sparklineOption} style={{ height: '100%', width: '100%' }} opts={{ renderer: 'canvas' }} />
          </div>
        ) : null}
      </div>
    </ChartSurface>
  );
};

export default OpsAnalysisSingle;

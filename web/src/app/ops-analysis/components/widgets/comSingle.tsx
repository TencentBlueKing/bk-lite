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
import { resolveSingleDescriptionText } from '@/app/ops-analysis/utils/singleDescription';
import {
  resolveSingleValueMetaLayout,
  SINGLE_META_TYPOGRAPHY,
} from '@/app/ops-analysis/utils/singleMetaTypography';
import { useTranslation } from '@/utils/i18n';
import OpsAnalysisMetricValue, {
  OPS_METRIC_DEFAULT_HEIGHT_FILL_RATIO,
  resolveMetricFontSize,
} from '@/app/ops-analysis/components/ops-analysis-metric-value';
import { useWidgetDataLink } from '@/app/ops-analysis/components/interactionTitleIcon';
import DataLinkHintTooltip from '@/app/ops-analysis/components/dataLinkHintTooltip';
import { buildInteractionPoints } from '@/app/ops-analysis/utils/interactionPoints';
import WidgetState from '@/app/ops-analysis/components/widget-state';
import { useWidgetViewport } from '@/app/ops-analysis/components/widget-viewport';
import {
  scaleScreenMetric,
  scaleScreenMetricFloat,
} from './shared/screenMetrics';
import { getModelIconUrl } from '@/app/cmdb/utils/modelIcon';
import {
  readSingleValueStyle,
  resolveSingleValueIconBox,
  resolveSingleValueIconSrc,
  type SingleValueContentAlign,
} from '@/app/ops-analysis/utils/singleValueStyle';

const MAX_SPARKLINE_POINTS = 24;
const UNIT_FONT_SCALE = 0.48;

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
  const { scale } = useWidgetViewport();
  const chartTheme = getOpsChartThemeByMode(config?.chartThemeMode);
  const usesScreenTheme = isScreenChartThemeMode(config?.chartThemeMode);
  const contentAreaRef = useRef<HTMLDivElement>(null);
  const iconRowRef = useRef<HTMLDivElement>(null);
  const textMeasureRef = useRef<HTMLSpanElement>(null);
  const [contentAreaHeight, setContentAreaHeight] = useState(0);
  const [iconRowWidth, setIconRowWidth] = useState(0);
  const [iconRowHeight, setIconRowHeight] = useState(0);
  const [valueTextWidth, setValueTextWidth] = useState(0);
  const [iconMeasure, setIconMeasure] = useState({ src: '', aspect: 1 });

  const selectedField = config?.selectedFields?.[0];
  const { active: dataLinkActive, openPoint, hoverHint } = useWidgetDataLink(config);
  const singlePoint = useMemo(
    () => buildInteractionPoints('single', rawData, config)[0],
    [config, rawData],
  );
  const rawValue = extractComparableValue(rawData, selectedField);
  const descriptionText = resolveSingleDescriptionText(
    rawData,
    config?.descriptionField,
  );
  const baselineRawValue = extractComparableValue(baselineData, selectedField);
  const numericValue = toComparableNumber(rawValue);
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
  const color = getColorByThreshold(numericValue, thresholds, chartTheme.singleValueColor);
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
  const sparklineAvailable =
    Boolean(config?.compare) && sparklineData.length > 1;
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

    const updateContentAreaHeight = () => {
      setContentAreaHeight((prev) =>
        prev === contentArea.clientHeight ? prev : contentArea.clientHeight,
      );
    };

    updateContentAreaHeight();

    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frameId);
      frameId = requestAnimationFrame(updateContentAreaHeight);
    });

    observer.observe(contentArea);

    return () => {
      cancelAnimationFrame(frameId);
      observer.disconnect();
    };
  }, [isDataReady, loading]);

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
  const showSparkline = sparklineAvailable;
  const sparklineHeight = showSparkline
    ? scaleScreenMetric(28, screenRenderContext) +
      scaleScreenMetric(6, screenRenderContext)
    : 0;
  const hasDescription = Boolean(descriptionText);
  const {
    typography: {
      descriptionFontSize,
      compareLabelFontSize,
      compareValueFontSize,
      spacing: metaSpacing,
    },
    mainSlotHeight,
    targetMainFontSize,
  } = resolveSingleValueMetaLayout({
    contentAreaHeight,
    sparklineHeight,
    scale,
    hasDescription,
    hasCompare: Boolean(config?.compare),
  });
  const sparklineTrendColor = config?.compare ? compareTextColor : metricColor;
  // 命中值映射文本时，用映射文本替换数值并隐藏单位
  const shownMainValue =
    valueMappingResult?.text !== undefined
      ? valueMappingResult.text
      : displayMainValue;
  const unitLabel = compareUnitLabel;
  const sparklineLineColor = useMemo(
    () => ({
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
    }),
    [sparklineTrendColor],
  );
  const sparklineAreaColor = useMemo(
    () => ({
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
    }),
    [sparklineTrendColor],
  );
  const singleStyle = readSingleValueStyle(config?.singleStyle);
  const iconSrc = resolveSingleValueIconSrc(singleStyle, (iconKey) =>
    getModelIconUrl({ icn: iconKey, model_id: '' }),
  );
  if ((iconSrc ?? '') !== iconMeasure.src) {
    setIconMeasure({ src: iconSrc ?? '', aspect: 1 });
  }
  const iconAspect = iconMeasure.src === (iconSrc ?? '') ? iconMeasure.aspect : 1;
  const handleIconLoad = (event: React.SyntheticEvent<HTMLImageElement>) => {
    const img = event.currentTarget;
    if (!(img.naturalWidth > 0) || !(img.naturalHeight > 0)) return;
    const next = img.naturalWidth / img.naturalHeight;
    setIconMeasure((prev) => {
      if (prev.src !== (iconSrc ?? '') || Math.abs(prev.aspect - next) < 0.02) return prev;
      return { src: prev.src, aspect: next };
    });
  };
  const iconFontSize = iconRowHeight > 0
    ? resolveMetricFontSize({
      height: iconRowHeight,
      width: iconRowWidth,
      scale,
      minVisibleFontSize: SINGLE_META_TYPOGRAPHY.minVisibleMainFont,
      maxVisibleFontSize: SINGLE_META_TYPOGRAPHY.maxVisibleMainFont,
      heightFillRatio: hasDescription
        ? SINGLE_META_TYPOGRAPHY.groupedMetricHeightFillRatio
        : OPS_METRIC_DEFAULT_HEIGHT_FILL_RATIO,
    })
    : targetMainFontSize;
  const iconBox = resolveSingleValueIconBox({
    rowWidth: iconRowWidth,
    fontSize: iconFontSize,
    textWidth: valueTextWidth,
    size: singleStyle.iconSize,
    aspect: iconAspect,
  });
  const iconVisible = Boolean(iconSrc) && iconBox.visible;
  const valueAlign: SingleValueContentAlign =
    singleStyle.align ?? (usesScreenTheme ? 'center' : 'left');
  const metaAlign: SingleValueContentAlign = singleStyle.align ?? 'left';
  const valueJustifyClass =
    valueAlign === 'center'
      ? 'justify-center'
      : valueAlign === 'right'
        ? 'justify-end'
        : 'justify-start';
  const metaJustifyClass =
    metaAlign === 'center'
      ? 'justify-center'
      : metaAlign === 'right'
        ? 'justify-end'
        : '';
  const metaTextAlign =
    metaAlign === 'center' ? 'center' : metaAlign === 'right' ? 'right' : undefined;
  const metricJustifyClass = iconVisible
    ? 'justify-start'
    : valueAlign === 'center'
      ? 'justify-center'
      : valueAlign === 'right'
        ? 'justify-end'
        : '';
  const valueSlotWidth =
    iconVisible && iconRowWidth > 0 && valueTextWidth > 0
      ? Math.min(
        valueTextWidth,
        Math.max(0, iconRowWidth - iconBox.width - iconBox.gap),
      )
      : undefined;

  useLayoutEffect(() => {
    const row = iconRowRef.current;
    if (!row) return undefined;

    let frameId = 0;
    const updateIconBox = () => {
      const nextRow = row.clientWidth;
      const nextHeight = row.clientHeight;
      const nextText = textMeasureRef.current?.offsetWidth ?? 0;
      setIconRowWidth((prev) => (prev === nextRow ? prev : nextRow));
      setIconRowHeight((prev) => (prev === nextHeight ? prev : nextHeight));
      setValueTextWidth((prev) => (prev === nextText ? prev : nextText));
    };

    updateIconBox();
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frameId);
      frameId = requestAnimationFrame(updateIconBox);
    });
    observer.observe(row);
    return () => {
      cancelAnimationFrame(frameId);
      observer.disconnect();
    };
  }, [isDataReady, loading, shownMainValue, iconFontSize, unitLabel]);

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
    <DataLinkHintTooltip hint={singlePoint ? hoverHint : undefined}>
    <div
      className={`flex h-full w-full flex-col overflow-hidden ${
        usesScreenTheme ? '' : 'px-2'
      } ${dataLinkActive && singlePoint ? 'cursor-pointer' : ''}`}
      onClick={dataLinkActive ? () => openPoint(singlePoint) : undefined}
    >
      <div
        ref={contentAreaRef}
        className="flex min-h-0 flex-1 flex-col"
      >
        <div
          data-testid="single-value-body"
          data-value-align={valueAlign}
          data-meta-align={metaAlign}
          className="flex min-h-0 flex-1 flex-col"
        >
        <div className="flex min-h-0 flex-1 flex-col justify-center">
          <div
            className={
              mainSlotHeight == null
                ? 'min-h-0 w-full flex-1'
                : 'w-full shrink-0'
            }
            style={
              mainSlotHeight == null ? undefined : { height: mainSlotHeight }
            }
          >
            <div
              ref={iconRowRef}
              className={`relative flex h-full w-full items-center ${valueJustifyClass}`}
            >
              <span
                ref={textMeasureRef}
                aria-hidden
                className="pointer-events-none absolute whitespace-nowrap font-semibold opacity-0"
                style={{
                  fontSize: iconFontSize,
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                {shownMainValue}
                {unitLabel ? (
                  <span
                    style={{
                      fontSize: `${UNIT_FONT_SCALE}em`,
                      marginLeft: '0.14em',
                    }}
                  >
                    {unitLabel}
                  </span>
                ) : null}
              </span>
              <div
                className={`flex h-full min-w-0 items-center ${
                  iconVisible && valueSlotWidth != null ? 'max-w-full' : 'w-full'
                }`}
                style={{ gap: iconVisible ? iconBox.gap : 0 }}
              >
                {iconVisible && singleStyle.iconPosition === 'left' && iconSrc ? (
                  <img
                    src={iconSrc}
                    alt=""
                    data-testid="single-value-icon"
                    draggable={false}
                    className="shrink-0 object-contain"
                    style={{ height: iconBox.size, width: 'auto' }}
                    onLoad={handleIconLoad}
                  />
                ) : null}
                <div
                  className="h-full min-w-0"
                  style={
                    valueSlotWidth == null
                      ? { flex: '1 1 auto', maxWidth: '100%' }
                      : { width: valueSlotWidth, flex: '0 0 auto', maxWidth: '100%' }
                  }
                >
                  <OpsAnalysisMetricValue
                    main={shownMainValue}
                    unit={unitLabel || undefined}
                    color={metricColor}
                    unitColor={toAlphaColor(metricColor, 0.78)}
                    className={`items-center ${metricJustifyClass}`}
                    valueClassName="font-semibold"
                    unitClassName="font-medium"
                    fontVariantNumeric="tabular-nums"
                    textShadow={chartTheme.singleValueGlow}
                    unitScale={UNIT_FONT_SCALE}
                    unitTransform="translateY(-0.02em)"
                    heightFillRatio={
                      hasDescription
                        ? SINGLE_META_TYPOGRAPHY.groupedMetricHeightFillRatio
                        : undefined
                    }
                  />
                </div>
                {iconVisible && singleStyle.iconPosition === 'right' && iconSrc ? (
                  <img
                    src={iconSrc}
                    alt=""
                    data-testid="single-value-icon"
                    draggable={false}
                    className="shrink-0 object-contain"
                    style={{ height: iconBox.size, width: 'auto' }}
                    onLoad={handleIconLoad}
                  />
                ) : null}
              </div>
            </div>
          </div>

          {descriptionText ? (
            <div
              data-testid="single-description"
              className="w-full min-w-0 shrink-0"
              style={{
                marginTop: metaSpacing,
                color: chartTheme.singleValueMetaColor,
                fontSize: descriptionFontSize,
                lineHeight: SINGLE_META_TYPOGRAPHY.descriptionLineHeight,
                textAlign: metaTextAlign,
              }}
            >
              <div className="line-clamp-2 break-words" title={descriptionText}>
                {descriptionText}
              </div>
            </div>
          ) : null}
        </div>

        {config?.compare && (
          <div
            data-testid="single-compare"
            className={`flex w-full min-w-0 shrink-0 flex-nowrap items-center gap-1 overflow-hidden ${metaJustifyClass}`}
            style={{
              marginTop: metaSpacing,
              color: chartTheme.singleValueMetaColor,
              lineHeight: SINGLE_META_TYPOGRAPHY.compareLineHeight,
            }}
          >
            <span
              className="min-w-0 truncate"
              style={{
                color: chartTheme.singleValueMetaColor,
                fontSize: compareLabelFontSize,
              }}
            >
              {t('dashboard.comparePreviousShortLabel')}
            </span>
            <span
              className="shrink-0 font-semibold"
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
    </DataLinkHintTooltip>
  );
};

export default ComSingle;

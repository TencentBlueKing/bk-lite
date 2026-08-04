'use client';

import React, { useCallback } from 'react';
import AutoFitMetricValue, {
  type AutoFitMetricValueProps,
  type AutoFitMetricValueSize,
} from '@/components/auto-fit-metric-value';
import {
  toCanvasPixels,
  useWidgetViewport,
} from '@/app/ops-analysis/components/widget-viewport';

const DEFAULT_MIN_VISIBLE_FONT_SIZE = 18;
const DEFAULT_MAX_VISIBLE_FONT_SIZE = 104;
const DEFAULT_HEIGHT_FILL_RATIO = 0.5;

export interface ResolveMetricFontSizeInput extends AutoFitMetricValueSize {
  scale: number;
  minVisibleFontSize: number;
  maxVisibleFontSize: number;
  heightFillRatio: number;
}

export const resolveMetricFontSize = ({
  height,
  scale,
  minVisibleFontSize,
  maxVisibleFontSize,
  heightFillRatio,
}: ResolveMetricFontSizeInput) => {
  const visibleHeight = Math.max(height, 0) * scale;
  const visibleFontSize = Math.max(
    minVisibleFontSize,
    Math.min(maxVisibleFontSize, visibleHeight * heightFillRatio),
  );
  return toCanvasPixels(visibleFontSize, scale);
};

export interface OpsAnalysisMetricValueProps
  extends Omit<
    AutoFitMetricValueProps,
    'resolveFontSize' | 'minFontSize' | 'gap'
  > {
  minVisibleFontSize?: number;
  maxVisibleFontSize?: number;
  heightFillRatio?: number;
  minVisibleGap?: number;
  maxVisibleGap?: number;
  gapRatio?: number;
}

const OpsAnalysisMetricValue: React.FC<OpsAnalysisMetricValueProps> = ({
  className = '',
  minVisibleFontSize = DEFAULT_MIN_VISIBLE_FONT_SIZE,
  maxVisibleFontSize = DEFAULT_MAX_VISIBLE_FONT_SIZE,
  heightFillRatio = DEFAULT_HEIGHT_FILL_RATIO,
  minVisibleGap = 4,
  maxVisibleGap = 16,
  gapRatio = 0.14,
  ...props
}) => {
  const { scale } = useWidgetViewport();
  const resolveFontSize = useCallback(
    (size: AutoFitMetricValueSize) =>
      resolveMetricFontSize({
        ...size,
        scale,
        minVisibleFontSize,
        maxVisibleFontSize,
        heightFillRatio,
      }),
    [heightFillRatio, maxVisibleFontSize, minVisibleFontSize, scale],
  );
  const resolveGap = useCallback(
    (fontSize: number) => {
      const visibleFontSize = fontSize * scale;
      const visibleGap = Math.max(
        minVisibleGap,
        Math.min(maxVisibleGap, visibleFontSize * gapRatio),
      );
      return toCanvasPixels(visibleGap, scale);
    },
    [gapRatio, maxVisibleGap, minVisibleGap, scale],
  );

  return (
    <AutoFitMetricValue
      {...props}
      className={`flex h-full w-full items-center ${className}`.trim()}
      minFontSize={toCanvasPixels(minVisibleFontSize, scale)}
      gap={resolveGap}
      resolveFontSize={resolveFontSize}
    />
  );
};

export default OpsAnalysisMetricValue;

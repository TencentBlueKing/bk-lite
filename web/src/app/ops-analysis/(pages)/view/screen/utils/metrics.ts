import type { ScreenDisplayAdapter } from '@/app/ops-analysis/types/screen';

export interface ScreenFitInput {
  contentWidth: number;
  contentHeight: number;
  designWidth: number;
  designHeight: number;
  adapter?: ScreenDisplayAdapter;
}

export interface ScreenFitMetrics {
  fitScale: number;
  scaleX: number;
  scaleY: number;
  renderedWidth: number;
  renderedHeight: number;
  overflowX: boolean;
  overflowY: boolean;
}

export interface ScreenVisualMetrics extends ScreenFitMetrics {
  screenDensity: number;
  screenUiScale: number;
}

export const clamp = (value: number, min: number, max: number) =>
  Math.min(Math.max(value, min), max);

const safePositiveNumber = (value: number, fallback: number) =>
  Number.isFinite(value) && value > 0 ? value : fallback;

const resolveAdapter = (adapter?: ScreenDisplayAdapter): ScreenDisplayAdapter => {
  if (
    adapter === 'contain' ||
    adapter === 'fill' ||
    adapter === 'fitWidth' ||
    adapter === 'fitHeight'
  ) {
    return adapter;
  }
  return 'fill';
};

export const calculateScreenFitMetrics = ({
  contentWidth,
  contentHeight,
  designWidth,
  designHeight,
  adapter,
}: ScreenFitInput): ScreenFitMetrics => {
  const safeDesignWidth = safePositiveNumber(designWidth, 1920);
  const safeDesignHeight = safePositiveNumber(designHeight, 1080);
  const safeContentWidth = Math.max(contentWidth, 0);
  const safeContentHeight = Math.max(contentHeight, 0);

  if (!safeContentWidth || !safeContentHeight) {
    return {
      fitScale: 1,
      scaleX: 1,
      scaleY: 1,
      renderedWidth: safeDesignWidth,
      renderedHeight: safeDesignHeight,
      overflowX: false,
      overflowY: false,
    };
  }

  const widthScale = safeContentWidth / safeDesignWidth;
  const heightScale = safeContentHeight / safeDesignHeight;
  const resolvedAdapter = resolveAdapter(adapter);
  const scaleX =
    resolvedAdapter === 'fitHeight'
      ? heightScale
      : resolvedAdapter === 'contain'
        ? Math.min(widthScale, heightScale)
        : widthScale;
  const scaleY =
    resolvedAdapter === 'fitWidth'
      ? widthScale
      : resolvedAdapter === 'contain'
        ? Math.min(widthScale, heightScale)
        : heightScale;
  const safeScaleX = Math.max(scaleX, 0.0001);
  const safeScaleY = Math.max(scaleY, 0.0001);
  const renderedWidth =
    resolvedAdapter === 'fill' || resolvedAdapter === 'fitWidth'
      ? safeContentWidth
      : Math.round(safeDesignWidth * safeScaleX);
  const renderedHeight =
    resolvedAdapter === 'fill' || resolvedAdapter === 'fitHeight'
      ? safeContentHeight
      : Math.round(safeDesignHeight * safeScaleY);

  return {
    fitScale: Math.min(safeScaleX, safeScaleY),
    scaleX: safeScaleX,
    scaleY: safeScaleY,
    renderedWidth,
    renderedHeight,
    overflowX: renderedWidth > safeContentWidth,
    overflowY: renderedHeight > safeContentHeight,
  };
};

export const calculateScreenVisualMetrics = (
  input: ScreenFitInput,
): ScreenVisualMetrics => {
  const fit = calculateScreenFitMetrics(input);
  const densityBase = Math.min(
    fit.renderedWidth / 1440,
    fit.renderedHeight / 810,
  );
  const screenDensity = clamp(densityBase, 0.72, 1.16);

  return {
    ...fit,
    screenDensity,
    screenUiScale: screenDensity / fit.fitScale,
  };
};

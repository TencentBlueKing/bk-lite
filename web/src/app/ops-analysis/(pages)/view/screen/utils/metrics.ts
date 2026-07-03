export interface ScreenFitInput {
  contentWidth: number;
  contentHeight: number;
  designWidth: number;
  designHeight: number;
}

export interface ScreenFitMetrics {
  fitScale: number;
  renderedWidth: number;
  renderedHeight: number;
}

export interface ScreenVisualMetrics extends ScreenFitMetrics {
  screenDensity: number;
  screenUiScale: number;
}

export const clamp = (value: number, min: number, max: number) =>
  Math.min(Math.max(value, min), max);

const safePositiveNumber = (value: number, fallback: number) =>
  Number.isFinite(value) && value > 0 ? value : fallback;

export const calculateScreenFitMetrics = ({
  contentWidth,
  contentHeight,
  designWidth,
  designHeight,
}: ScreenFitInput): ScreenFitMetrics => {
  const safeDesignWidth = safePositiveNumber(designWidth, 1920);
  const safeDesignHeight = safePositiveNumber(designHeight, 1080);
  const safeContentWidth = Math.max(contentWidth, 0);
  const safeContentHeight = Math.max(contentHeight, 0);

  if (!safeContentWidth || !safeContentHeight) {
    return {
      fitScale: 1,
      renderedWidth: safeDesignWidth,
      renderedHeight: safeDesignHeight,
    };
  }

  const fitScale = Math.max(
    Math.min(
      safeContentWidth / safeDesignWidth,
      safeContentHeight / safeDesignHeight,
    ),
    0.0001,
  );

  return {
    fitScale,
    renderedWidth: Math.floor(safeDesignWidth * fitScale),
    renderedHeight: Math.floor(safeDesignHeight * fitScale),
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

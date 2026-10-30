import type {
  ScreenLayoutMode,
  ScreenRenderContext,
} from '@/app/ops-analysis/types/dashBoard';
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

export interface DesignBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** 呈现层几何。设计坐标不改，调用方不得把结果写回草稿。 */
export const mapDesignBoxToViewportPixels = (
  box: DesignBox,
  scaleX: number,
  scaleY: number,
): DesignBox => {
  const safeX = Number.isFinite(scaleX) ? scaleX : 1;
  const safeY = Number.isFinite(scaleY) ? scaleY : 1;
  return {
    x: Math.round(box.x * safeX),
    y: Math.round(box.y * safeY),
    w: Math.max(1, Math.round(box.w * safeX)),
    h: Math.max(1, Math.round(box.h * safeY)),
  };
};

/** 把设计字号乘密度后写成 CSS 像素。密度由调用方决定。 */
export const scalePresentedFontPx = (designPx: number, density: number) => {
  const safeDensity = Number.isFinite(density) && density > 0 ? density : 1;
  return Math.max(1, Math.round(designPx * safeDensity));
};

/**
 * 视口像素没有外层 transform。
 * 字号用 screenDensity，等于旧路径 designPx × screenUiScale × fitScale 的屏幕结果。
 * fitScale 只描述几何：4K 设计稿缩进 1080p 时它约 0.5，字号若再跟它会比查看页小一倍。
 */
export const resolvePresentedUiScale = (
  layoutMode: ScreenLayoutMode,
  screenDensity: number,
  transformUiScale: number,
) => (layoutMode === 'viewportPixels' ? screenDensity : transformUiScale);

/**
 * 标题、时钟和其它 chrome 文字。
 * 编辑态写的是设计 px，外层 transform 再乘 fitScale。
 * 视口像素没有这层 transform，所以直接乘 fitScale，比例才和编辑态一致。
 * 图表另用 screenDensity；标题不要跟那一档，否则 4K 盘名会比编辑态大约一倍。
 */
export const resolveChromeFontDensity = (
  layoutMode: ScreenLayoutMode,
  fitScale: number,
) => {
  if (layoutMode !== 'viewportPixels') return 1;
  return Number.isFinite(fitScale) && fitScale > 0 ? fitScale : 1;
};

/** 图表视口倍数表示外层 CSS transform。没有 transform 时为 1，避免再除一次。 */
export const resolveWidgetViewportScale = (
  layoutMode: ScreenLayoutMode,
  fitScale: number,
) => (layoutMode === 'viewportPixels' ? 1 : fitScale);

export const presentScreenRenderContext = ({
  layoutMode,
  fitScale,
  scaleX,
  scaleY,
  screenDensity,
  transformUiScale,
}: {
  layoutMode: ScreenLayoutMode;
  fitScale: number;
  scaleX: number;
  scaleY: number;
  screenDensity: number;
  transformUiScale: number;
}): {
  context: ScreenRenderContext;
  widgetViewportScale: number;
} => {
  const uiScale = resolvePresentedUiScale(layoutMode, screenDensity, transformUiScale);
  return {
    context: {
      enabled: true,
      fitScale,
      scaleX,
      scaleY,
      screenDensity,
      screenUiScale: uiScale,
      widgetDensity: screenDensity,
      widgetUiScale: uiScale,
      layoutMode,
    },
    widgetViewportScale: resolveWidgetViewportScale(layoutMode, fitScale),
  };
};

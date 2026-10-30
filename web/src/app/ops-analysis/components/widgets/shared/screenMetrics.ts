import type { ScreenRenderContext } from '@/app/ops-analysis/types/dashBoard';

export const getScreenWidgetScale = (
  screenRenderContext?: ScreenRenderContext,
) => {
  if (!screenRenderContext?.enabled) return 1;
  // viewportPixels 的 uiScale 已是屏幕密度。这里只乘这一次，不再假设外层还有 transform。
  return screenRenderContext.widgetUiScale || screenRenderContext.screenUiScale || 1;
};

export const scaleScreenMetric = (
  value: number,
  screenRenderContext?: ScreenRenderContext,
) => Math.round(value * getScreenWidgetScale(screenRenderContext));

export const scaleScreenMetricFloat = (
  value: number,
  screenRenderContext?: ScreenRenderContext,
) => Number((value * getScreenWidgetScale(screenRenderContext)).toFixed(2));

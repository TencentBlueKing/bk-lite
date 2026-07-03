import type { ScreenRenderContext } from '@/app/ops-analysis/types/dashBoard';

export const getScreenWidgetScale = (
  screenRenderContext?: ScreenRenderContext,
) =>
  screenRenderContext?.enabled
    ? screenRenderContext.widgetUiScale || screenRenderContext.screenUiScale || 1
    : 1;

export const scaleScreenMetric = (
  value: number,
  screenRenderContext?: ScreenRenderContext,
) => Math.round(value * getScreenWidgetScale(screenRenderContext));

export const scaleScreenMetricFloat = (
  value: number,
  screenRenderContext?: ScreenRenderContext,
) => Number((value * getScreenWidgetScale(screenRenderContext)).toFixed(2));

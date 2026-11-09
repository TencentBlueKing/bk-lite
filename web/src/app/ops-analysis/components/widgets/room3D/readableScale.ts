import type { ScreenRenderContext } from '@/app/ops-analysis/types/dashBoard';

type ReadableScaleInput = Pick<
  ScreenRenderContext,
  'enabled' | 'fitScale' | 'widgetUiScale' | 'screenUiScale' | 'layoutMode'
>;

/**
 * 机柜字号画在组件盒子里。
 * 设计画布还有外层 transform，所以用 1/fitScale 抵消缩小。
 * 视口像素布局没有这层 transform，uiScale 已经是屏幕密度，不能再取倒数。
 */
export const resolveRoom3DReadableScale = (
  context?: ReadableScaleInput | null,
) => {
  if (!context?.enabled) return 1;
  const fitScale =
    Number.isFinite(context.fitScale) && context.fitScale > 0
      ? context.fitScale
      : 1;
  const uiScale = context.widgetUiScale || context.screenUiScale || 1;
  if (context.layoutMode === 'viewportPixels') return uiScale;
  return Math.max(uiScale, 1 / fitScale, 1);
};

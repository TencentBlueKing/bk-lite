import type { ScreenRenderContext } from '@/app/ops-analysis/types/dashBoard';

/** 菜单基础字号。机柜悬停卡正文是 12px。 */
export const INTERACTION_MENU_FONT_PX = 12;
/** 再小就不好认，12 × 倍数不得低于这个字号。 */
export const INTERACTION_MENU_FONT_FLOOR_PX = 10;
export const INTERACTION_MENU_SCALE_MIN =
  INTERACTION_MENU_FONT_FLOOR_PX / INTERACTION_MENU_FONT_PX;
export const INTERACTION_MENU_SCALE_MAX = 1.6;
/** 不在大屏里，或算不出倍数时，用紧凑基准，不再放大。 */
const NEUTRAL_SCALE = 1;

const positive = (value: number | undefined): number | undefined =>
  typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : undefined;

const sameScale = (left: number, right: number) => Math.abs(left - right) <= 0.001;

type MenuScaleInput = Pick<
  ScreenRenderContext,
  'enabled' | 'fitScale' | 'scaleX' | 'scaleY' | 'widgetUiScale' | 'screenUiScale'
>;

/**
 * 把倍数收进可读范围。下限是 10px 字号（约 0.84），上限 1.6。
 * 没有「不小于 1」：画布比设计稿小时菜单要跟着变小。
 */
export const clampInteractionMenuScale = (raw: number): number => {
  if (!Number.isFinite(raw) || raw <= 0) return NEUTRAL_SCALE;
  const rounded = Math.round(raw * 1000) / 1000;
  return Math.min(
    INTERACTION_MENU_SCALE_MAX,
    Math.max(INTERACTION_MENU_SCALE_MIN, rounded),
  );
};

/**
 * 大屏组件实际画出来的倍数。查看和编辑用 contain，scaleX 与 scaleY 相等，
 * 这一轴就是 CSS transform 的倍数。全屏把两轴拉开时菜单不能跟着拉变形，改用 fitScale。
 */
export const resolveCanvasContentScale = (context: MenuScaleInput): number => {
  const scaleX = positive(context.scaleX);
  const scaleY = positive(context.scaleY);
  const uniformAxis = scaleX != null && scaleY != null && sameScale(scaleX, scaleY)
    ? scaleX
    : undefined;
  return uniformAxis
    ?? positive(context.fitScale)
    ?? (scaleX != null && scaleY != null ? Math.min(scaleX, scaleY) : undefined)
    ?? NEUTRAL_SCALE;
};

/**
 * 大屏菜单倍数 = 画布实际倍数 × 组件 ui-scale。
 * 仪表盘、报表、拓扑页不在大屏里，固定为 1，只用紧凑基准。
 */
export const resolveInteractionMenuScale = (
  context?: MenuScaleInput | null,
): number => {
  if (!context?.enabled) return NEUTRAL_SCALE;
  const uiScale = positive(context.widgetUiScale)
    ?? positive(context.screenUiScale)
    ?? NEUTRAL_SCALE;
  return clampInteractionMenuScale(resolveCanvasContentScale(context) * uiScale);
};

/**
 * 机柜悬停卡画在画布 transform 里面，自己的字号再乘 readableScale。
 * 菜单 portal 到 body，要和卡片在屏幕上一样大，得用 readableScale × 画布倍数。
 * 应用 3D 和拓扑没有这层反向放大，继续走画布倍数。
 */
export const resolvePortaledMenuScale = (
  inCanvasScale: number | undefined,
  context?: MenuScaleInput | null,
): number => {
  if (!context?.enabled) return NEUTRAL_SCALE;
  const overlay = positive(inCanvasScale) ?? NEUTRAL_SCALE;
  return clampInteractionMenuScale(overlay * resolveCanvasContentScale(context));
};

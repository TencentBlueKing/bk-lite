/**
 * 边中点拉动点的屏幕像素阈值。
 * 四角和边中点都是 8px 方块，角点向内伸出约 4px，边中点半宽 4px。
 * 某一边屏幕像素为 48 时，角点与边中点之间还留约 16px；再小就会挤在一起，
 * 因此小于 48px 时隐藏该方向的边中点，只留四角。
 */
export const SCREEN_EDGE_HANDLE_MIN_SCREEN_PX = 48;

export interface ScreenResizeEnablement {
  top: boolean;
  right: boolean;
  bottom: boolean;
  left: boolean;
  topRight: boolean;
  bottomRight: boolean;
  bottomLeft: boolean;
  topLeft: boolean;
}

const safeScale = (scale: number) =>
  Number.isFinite(scale) && scale > 0 ? scale : 1;

export const getScreenResizeEnablement = ({
  editable,
  selected,
  width,
  height,
  scaleX,
  scaleY = scaleX,
}: {
  editable: boolean;
  selected: boolean;
  width: number;
  height: number;
  scaleX: number;
  scaleY?: number;
}): ScreenResizeEnablement => {
  const corners = editable && selected;
  // 上下边中点沿宽度方向排列，左右边中点沿高度方向排列。
  const showNorthSouth =
    width * safeScale(scaleX) >= SCREEN_EDGE_HANDLE_MIN_SCREEN_PX;
  const showEastWest =
    height * safeScale(scaleY) >= SCREEN_EDGE_HANDLE_MIN_SCREEN_PX;

  return {
    top: corners && showNorthSouth,
    right: corners && showEastWest,
    bottom: corners && showNorthSouth,
    left: corners && showEastWest,
    topRight: corners,
    bottomRight: corners,
    bottomLeft: corners,
    topLeft: corners,
  };
};

const TRANSLATE_PX =
  /translate\(\s*(-?\d+(?:\.\d+)?)px\s*,\s*(-?\d+(?:\.\d+)?)px\s*\)/;

export const readTranslatePx = (
  transform: string,
): { x: number; y: number } | null => {
  const match = TRANSLATE_PX.exec(transform);
  if (!match) return null;
  const x = Number(match[1]);
  const y = Number(match[2]);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  return { x, y };
};

export interface ScreenResizeBox {
  style: { transform: string };
  offsetWidth: number;
  offsetHeight: number;
}

/**
 * react-rnd 回调里的 position 会叠一层按单一 scale 算出的 offset。
 * 画布在 fill 下 scaleX 与 scaleY 不同，拖上边或左边时这个 offset 会把 x/y 带偏。
 * 拖拽库写在节点上的 translate 才是布局坐标，优先用它。
 */
export const screenGeometryFromResize = (
  element: ScreenResizeBox,
  reportedPosition: { x: number; y: number },
) => {
  const translated = readTranslatePx(element.style.transform);
  return {
    x: Math.round(translated?.x ?? reportedPosition.x),
    y: Math.round(translated?.y ?? reportedPosition.y),
    w: Math.round(element.offsetWidth),
    h: Math.round(element.offsetHeight),
  };
};

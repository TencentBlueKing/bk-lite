import type { NodeStatusLevel, RectangleBorderLevel } from 'src/types';

export const STATUS_GRAY = '#9ca3af';
// Matches monitor LEVEL_MAP.warning.
export const WARNING_AMBER = '#FFAD42';
// Matches monitor LEVEL_MAP.critical / theme statusError.
export const CRITICAL_RED = '#F43B2C';
// Matches theme statusSuccess.
export const SUCCESS_GREEN = '#27C274';
export const BRAND_BLUE = '#155aef';

export const NODE_STATUS_COLOR: Record<NodeStatusLevel, string> = {
  normal: SUCCESS_GREEN,
  warning: WARNING_AMBER,
  critical: CRITICAL_RED,
  unmonitored: STATUS_GRAY,
  unknown: STATUS_GRAY,
  invalid: '#c2410c',
  forbidden: STATUS_GRAY
};

/** Corner count badges on icon name plates and area corners. */
export const ALERT_BADGE_TONE: Partial<Record<NodeStatusLevel, { bg: string; fg: string }>> = {
  warning: { bg: WARNING_AMBER, fg: '#1f2937' },
  critical: { bg: CRITICAL_RED, fg: '#fff' }
};

export const RECTANGLE_BORDER_COLOR: Record<RectangleBorderLevel, string> = {
  warning: WARNING_AMBER,
  critical: CRITICAL_RED,
  unknown: STATUS_GRAY
};

/** View-mode selection. Matches the app brand blue (`--color-primary` fallback). */
export const HIGHLIGHT_STROKE = BRAND_BLUE;

// Unprojected SVG units. The isometric matrix scales this toward a 2px screen edge.
export const RECTANGLE_STATUS_STROKE_WIDTH = 4;
export const RECTANGLE_STATUS_STROKE_HOVER_WIDTH = 7;

export const withAlpha = (hex: string, alpha: number) => {
  const raw = hex.replace('#', '');
  const value = raw.length === 3 ? raw.split('').map((char) => char + char).join('') : raw;
  const red = Number.parseInt(value.slice(0, 2), 16);
  const green = Number.parseInt(value.slice(2, 4), 16);
  const blue = Number.parseInt(value.slice(4, 6), 16);

  return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
};

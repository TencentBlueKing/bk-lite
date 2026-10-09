import type { CSSProperties } from 'react';
import type {
  ScreenShapeGradientDirection,
  ScreenShapeKind,
  ScreenShapeStyle,
} from '@/app/ops-analysis/types/screen';

export const SCREEN_SHAPE_KINDS: ScreenShapeKind[] = [
  'rect',
  'circle',
  'roundedRect',
];

export const DEFAULT_SCREEN_SHAPE_STYLE: ScreenShapeStyle = {
  backgroundColor: 'rgba(4, 165, 180, 0.10)',
  hideBackground: false,
  borderColor: 'rgba(4, 165, 180, 1)',
  borderWidth: 1,
  hideBorder: false,
  shadow: 10,
  gradient: false,
  gradientDirection: 'vertical',
  gradientStart: 'rgba(4, 165, 180, 0.40)',
  gradientEnd: 'rgba(4, 165, 180, 0.05)',
};

const ROUNDED_RECT_RADIUS = 30;

const clampNumber = (
  value: unknown,
  min: number,
  max: number,
  fallback: number,
) => {
  if (typeof value !== 'number' || !Number.isFinite(value)) return fallback;
  return Math.min(max, Math.max(min, value));
};

const colorOr = (value: unknown, fallback: string) =>
  typeof value === 'string' && value.trim() ? value : fallback;

export const resolveScreenShapeKind = (value: unknown): ScreenShapeKind =>
  SCREEN_SHAPE_KINDS.includes(value as ScreenShapeKind)
    ? (value as ScreenShapeKind)
    : 'rect';

export const resolveScreenShapeStyle = (
  value?: Partial<ScreenShapeStyle> | null,
): ScreenShapeStyle => {
  const source = value || {};
  const direction: ScreenShapeGradientDirection =
    source.gradientDirection === 'horizontal' ? 'horizontal' : 'vertical';
  return {
    backgroundColor: colorOr(
      source.backgroundColor,
      DEFAULT_SCREEN_SHAPE_STYLE.backgroundColor,
    ),
    hideBackground: Boolean(source.hideBackground),
    borderColor: colorOr(source.borderColor, DEFAULT_SCREEN_SHAPE_STYLE.borderColor),
    borderWidth: clampNumber(source.borderWidth, 0, 40, DEFAULT_SCREEN_SHAPE_STYLE.borderWidth),
    hideBorder: Boolean(source.hideBorder),
    shadow: clampNumber(source.shadow, 0, 80, DEFAULT_SCREEN_SHAPE_STYLE.shadow),
    gradient: Boolean(source.gradient),
    gradientDirection: direction,
    gradientStart: colorOr(source.gradientStart, DEFAULT_SCREEN_SHAPE_STYLE.gradientStart),
    gradientEnd: colorOr(source.gradientEnd, DEFAULT_SCREEN_SHAPE_STYLE.gradientEnd),
  };
};

export const screenShapeCss = (
  shape: ScreenShapeKind,
  style?: Partial<ScreenShapeStyle> | null,
): CSSProperties => {
  const resolved = resolveScreenShapeStyle(style);
  const gradientDirection = resolved.gradientDirection === 'horizontal' ? 'right' : 'top';
  const background = resolved.hideBackground
    ? 'transparent'
    : resolved.gradient
      ? `linear-gradient(to ${gradientDirection}, ${resolved.gradientStart} 1%, ${resolved.gradientEnd} 100%)`
      : resolved.backgroundColor;

  return {
    width: '100%',
    height: '100%',
    boxSizing: 'border-box',
    background,
    borderStyle: resolved.hideBorder ? 'none' : 'solid',
    borderColor: resolved.hideBorder ? 'transparent' : resolved.borderColor,
    borderWidth: resolved.hideBorder ? 0 : resolved.borderWidth,
    boxShadow:
      resolved.shadow > 0
        ? `0 0 ${resolved.shadow}px 0 rgba(255, 255, 255, 0.55)`
        : 'none',
    borderRadius:
      shape === 'circle' ? '50%' : shape === 'roundedRect' ? ROUNDED_RECT_RADIUS : 0,
  };
};

export const SINGLE_META_TYPOGRAPHY = {
  descriptionRatio: 0.085,
  compareLabelRatio: 0.07,
  compareValueRatio: 0.09,
  spacingRatio: 0.04,
  descriptionMinVisible: 12,
  descriptionMaxVisible: 22,
  compareLabelMinVisible: 12,
  compareLabelMaxVisible: 20,
  compareValueMinVisible: 14,
  compareValueMaxVisible: 24,
  spacingMinVisible: 6,
  spacingMaxVisible: 16,
  descriptionLineHeight: 1.3,
  descriptionMaxLines: 2,
  compareLineHeight: 1.2,
  groupedMetricHeightFillRatio: 0.92,
  maxVisibleMainFont: 104,
  mainSlotMinVisible: 36,
} as const;

export interface SingleMetaTypography {
  descriptionFontSize: number;
  compareLabelFontSize: number;
  compareValueFontSize: number;
  spacing: number;
}

export interface ResolveSingleMetaTypographyInput {
  contentAreaHeight: number;
  scale?: number;
}

const toCanvasPixels = (visible: number, scale: number) => {
  const safeScale = Number.isFinite(scale) && scale > 0 ? scale : 1;
  return visible / safeScale;
};

const clamp = (value: number, min: number, max: number) =>
  Number(Math.max(min, Math.min(max, value)).toFixed(2));

/** 辅助文字只跟卡片高度走，不跟主值自适应字号，避免互相改布局导致抖动。 */
export const resolveSingleMetaTypography = ({
  contentAreaHeight,
  scale = 1,
}: ResolveSingleMetaTypographyInput): SingleMetaTypography => {
  const height = Math.max(contentAreaHeight, 0);

  return {
    descriptionFontSize: clamp(
      height * SINGLE_META_TYPOGRAPHY.descriptionRatio,
      toCanvasPixels(SINGLE_META_TYPOGRAPHY.descriptionMinVisible, scale),
      toCanvasPixels(SINGLE_META_TYPOGRAPHY.descriptionMaxVisible, scale),
    ),
    compareLabelFontSize: clamp(
      height * SINGLE_META_TYPOGRAPHY.compareLabelRatio,
      toCanvasPixels(SINGLE_META_TYPOGRAPHY.compareLabelMinVisible, scale),
      toCanvasPixels(SINGLE_META_TYPOGRAPHY.compareLabelMaxVisible, scale),
    ),
    compareValueFontSize: clamp(
      height * SINGLE_META_TYPOGRAPHY.compareValueRatio,
      toCanvasPixels(SINGLE_META_TYPOGRAPHY.compareValueMinVisible, scale),
      toCanvasPixels(SINGLE_META_TYPOGRAPHY.compareValueMaxVisible, scale),
    ),
    spacing: clamp(
      height * SINGLE_META_TYPOGRAPHY.spacingRatio,
      toCanvasPixels(SINGLE_META_TYPOGRAPHY.spacingMinVisible, scale),
      toCanvasPixels(SINGLE_META_TYPOGRAPHY.spacingMaxVisible, scale),
    ),
  };
};

export const resolveSingleMetaBlockHeight = ({
  hasDescription,
  hasCompare,
  typography,
}: {
  hasDescription: boolean;
  hasCompare: boolean;
  typography: SingleMetaTypography;
}) => {
  let height = 0;
  if (hasDescription) {
    height +=
      typography.spacing +
      typography.descriptionFontSize *
        SINGLE_META_TYPOGRAPHY.descriptionLineHeight *
        SINGLE_META_TYPOGRAPHY.descriptionMaxLines;
  }
  if (hasCompare) {
    height +=
      typography.spacing +
      typography.compareValueFontSize *
        SINGLE_META_TYPOGRAPHY.compareLineHeight;
  }
  return Number(height.toFixed(2));
};

export const resolveSingleMainSlotHeight = ({
  contentAreaHeight,
  metaBlockHeight,
  sparklineHeight,
  scale = 1,
}: {
  contentAreaHeight: number;
  metaBlockHeight: number;
  sparklineHeight: number;
  scale?: number;
}) => {
  if (contentAreaHeight <= 0) return null;

  const available = Math.max(
    0,
    contentAreaHeight - metaBlockHeight - sparklineHeight,
  );
  const minSlot = toCanvasPixels(
    SINGLE_META_TYPOGRAPHY.mainSlotMinVisible,
    scale,
  );
  const cap = toCanvasPixels(
    SINGLE_META_TYPOGRAPHY.maxVisibleMainFont,
    scale,
  ) / SINGLE_META_TYPOGRAPHY.groupedMetricHeightFillRatio;
  return Number(Math.min(available, Math.max(minSlot, cap)).toFixed(2));
};

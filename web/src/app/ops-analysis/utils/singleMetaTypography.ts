export const SINGLE_META_TYPOGRAPHY = {
  /** 说明相对「高度目标主值」的比例 */
  descriptionOfMainRatio: 0.26,
  compareLabelOfMainRatio: 0.18,
  compareValueOfMainRatio: 0.22,
  spacingOfMainRatio: 0.08,
  descriptionMinVisible: 12,
  descriptionMaxVisible: 28,
  compareLabelMinVisible: 12,
  compareLabelMaxVisible: 24,
  compareValueMinVisible: 14,
  compareValueMaxVisible: 28,
  spacingMinVisible: 6,
  spacingMaxVisible: 16,
  descriptionLineHeight: 1.3,
  descriptionMaxLines: 2,
  compareLineHeight: 1.2,
  groupedMetricHeightFillRatio: 0.92,
  minVisibleMainFont: 18,
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
  /** 高度推导的目标主值字号（canvas px），非宽度拟合后的最终字号 */
  targetMainFontSize: number;
  scale?: number;
}

export interface ResolveSingleValueMetaLayoutInput {
  contentAreaHeight: number;
  sparklineHeight?: number;
  scale?: number;
  hasDescription?: boolean;
  hasCompare?: boolean;
}

export interface SingleValueMetaLayout {
  typography: SingleMetaTypography;
  /** 有说明时约束主值槽；无说明时为 null，交给 flex 填满 */
  mainSlotHeight: number | null;
  /** 与辅助字共用的高度目标主值（未做宽度收缩） */
  targetMainFontSize: number;
}

const toCanvasPixels = (visible: number, scale: number) => {
  const safeScale = Number.isFinite(scale) && scale > 0 ? scale : 1;
  return visible / safeScale;
};

const clamp = (value: number, min: number, max: number) =>
  Number(Math.max(min, Math.min(max, value)).toFixed(2));

const metaHeightPerMainUnit = ({
  hasDescription,
  hasCompare,
}: {
  hasDescription: boolean;
  hasCompare: boolean;
}) => {
  let perMain = 0;
  if (hasDescription) {
    perMain +=
      SINGLE_META_TYPOGRAPHY.spacingOfMainRatio +
      SINGLE_META_TYPOGRAPHY.descriptionOfMainRatio *
        SINGLE_META_TYPOGRAPHY.descriptionLineHeight *
        SINGLE_META_TYPOGRAPHY.descriptionMaxLines;
  }
  if (hasCompare) {
    perMain +=
      SINGLE_META_TYPOGRAPHY.spacingOfMainRatio +
      SINGLE_META_TYPOGRAPHY.compareValueOfMainRatio *
        SINGLE_META_TYPOGRAPHY.compareLineHeight;
  }
  return perMain;
};

/** 辅助文字跟高度目标主值走；不跟宽度拟合后的主值，避免互相改布局导致抖动。 */
export const resolveSingleMetaTypography = ({
  targetMainFontSize,
  scale = 1,
}: ResolveSingleMetaTypographyInput): SingleMetaTypography => {
  const main = Math.max(targetMainFontSize, 0);

  return {
    descriptionFontSize: clamp(
      main * SINGLE_META_TYPOGRAPHY.descriptionOfMainRatio,
      toCanvasPixels(SINGLE_META_TYPOGRAPHY.descriptionMinVisible, scale),
      toCanvasPixels(SINGLE_META_TYPOGRAPHY.descriptionMaxVisible, scale),
    ),
    compareLabelFontSize: clamp(
      main * SINGLE_META_TYPOGRAPHY.compareLabelOfMainRatio,
      toCanvasPixels(SINGLE_META_TYPOGRAPHY.compareLabelMinVisible, scale),
      toCanvasPixels(SINGLE_META_TYPOGRAPHY.compareLabelMaxVisible, scale),
    ),
    compareValueFontSize: clamp(
      main * SINGLE_META_TYPOGRAPHY.compareValueOfMainRatio,
      toCanvasPixels(SINGLE_META_TYPOGRAPHY.compareValueMinVisible, scale),
      toCanvasPixels(SINGLE_META_TYPOGRAPHY.compareValueMaxVisible, scale),
    ),
    spacing: clamp(
      main * SINGLE_META_TYPOGRAPHY.spacingOfMainRatio,
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
  const cap =
    toCanvasPixels(SINGLE_META_TYPOGRAPHY.maxVisibleMainFont, scale) /
    SINGLE_META_TYPOGRAPHY.groupedMetricHeightFillRatio;
  return Number(Math.min(available, Math.max(minSlot, cap)).toFixed(2));
};

/**
 * 一次性划分主值槽与辅助字：先按理想比例闭式求目标主值，再生成 meta；
 * 实际槽位由 meta 回推，主值只可能 ≤ 目标，辅助字不再回写。
 */
export const resolveSingleValueMetaLayout = ({
  contentAreaHeight,
  sparklineHeight = 0,
  scale = 1,
  hasDescription = false,
  hasCompare = false,
}: ResolveSingleValueMetaLayoutInput): SingleValueMetaLayout => {
  const minMain = toCanvasPixels(
    SINGLE_META_TYPOGRAPHY.minVisibleMainFont,
    scale,
  );
  const maxMain = toCanvasPixels(
    SINGLE_META_TYPOGRAPHY.maxVisibleMainFont,
    scale,
  );
  const fill = SINGLE_META_TYPOGRAPHY.groupedMetricHeightFillRatio;
  const usable = Math.max(0, contentAreaHeight - sparklineHeight);

  if (usable <= 0) {
    const typography = resolveSingleMetaTypography({
      targetMainFontSize: minMain,
      scale,
    });
    return {
      typography,
      mainSlotHeight: null,
      targetMainFontSize: minMain,
    };
  }

  const metaPerMain = metaHeightPerMainUnit({ hasDescription, hasCompare });
  let targetMain =
    metaPerMain > 0
      ? (fill * usable) / (1 + fill * metaPerMain)
      : Math.min(maxMain, Math.max(minMain, usable * 0.5));

  targetMain = clamp(targetMain, minMain, maxMain);

  const typography = resolveSingleMetaTypography({
    targetMainFontSize: targetMain,
    scale,
  });

  if (!hasDescription) {
    return {
      typography,
      mainSlotHeight: null,
      targetMainFontSize: targetMain,
    };
  }

  const metaBlockHeight = resolveSingleMetaBlockHeight({
    hasDescription,
    hasCompare,
    typography,
  });
  const mainSlotHeight = resolveSingleMainSlotHeight({
    contentAreaHeight,
    metaBlockHeight,
    sparklineHeight,
    scale,
  });

  return {
    typography,
    mainSlotHeight,
    targetMainFontSize: targetMain,
  };
};

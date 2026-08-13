export type GaugeLayoutTier = 'small' | 'medium' | 'large';

export interface GaugeResponsiveLayout {
  tier: GaugeLayoutTier;
  splitNumber: number;
  axisLabelDistance: number;
  detailOffsetCenterY: string;
  detailFontSize: number;
}

export interface GaugeLayoutMeasureInput {
  width: number;
  height: number;
  gaugeShape?: 'semicircle' | 'circle';
  previousTier?: GaugeLayoutTier;
}

/** ECharts gauge radius % against min(width/2, height/2). */
const GAUGE_RADIUS_RATIO = {
  semicircle: 1.08,
  circle: 0.9,
} as const;

/** Hysteresis bands on estimated effective radius (px). */
const TIER_BANDS = {
  smallMedium: { enterMedium: 78, leaveMedium: 70 },
  mediumLarge: { enterLarge: 125, leaveLarge: 115 },
} as const;

export function estimateGaugeEffectiveRadius(
  width: number,
  height: number,
  isCircle: boolean,
): number {
  if (width <= 0 || height <= 0) {
    return 0;
  }

  const halfMin = Math.min(width, height) / 2;
  return halfMin * (isCircle ? GAUGE_RADIUS_RATIO.circle : GAUGE_RADIUS_RATIO.semicircle);
}

export function resolveGaugeLayoutTier(
  effectiveRadius: number,
  previousTier: GaugeLayoutTier = 'medium',
): GaugeLayoutTier {
  const { smallMedium, mediumLarge } = TIER_BANDS;

  if (previousTier === 'small') {
    if (effectiveRadius >= mediumLarge.enterLarge) {
      return 'large';
    }
    if (effectiveRadius >= smallMedium.enterMedium) {
      return 'medium';
    }
    return 'small';
  }

  if (previousTier === 'large') {
    if (effectiveRadius < smallMedium.leaveMedium) {
      return 'small';
    }
    if (effectiveRadius < mediumLarge.leaveLarge) {
      return 'medium';
    }
    return 'large';
  }

  if (effectiveRadius < smallMedium.leaveMedium) {
    return 'small';
  }
  if (effectiveRadius >= mediumLarge.enterLarge) {
    return 'large';
  }
  return 'medium';
}

export function getGaugeResponsiveLayout(
  input: GaugeLayoutMeasureInput,
): GaugeResponsiveLayout {
  const isCircle = input.gaugeShape === 'circle';
  const effectiveRadius = estimateGaugeEffectiveRadius(
    input.width,
    input.height,
    isCircle,
  );
  const tier =
    input.width <= 0 || input.height <= 0
      ? 'medium'
      : resolveGaugeLayoutTier(effectiveRadius, input.previousTier);

  const splitNumber = tier === 'small' ? 2 : tier === 'medium' ? 5 : 10;
  const axisLabelDistance = tier === 'small' ? 27 : tier === 'medium' ? 26 : 25;

  let detailOffsetCenterY: string;
  if (isCircle) {
    detailOffsetCenterY =
      tier === 'small' ? '72%' : tier === 'medium' ? '68%' : '66%';
  } else {
    detailOffsetCenterY =
      tier === 'small' ? '50%' : tier === 'medium' ? '42%' : '38%';
  }

  // Very short containers: keep detail inside the widget without crowding min/max.
  let detailFontSize = tier === 'small' ? 22 : tier === 'medium' ? 24 : 26;
  if (!isCircle && input.height > 0 && input.height < 115) {
    const current = Number.parseFloat(detailOffsetCenterY);
    detailOffsetCenterY = `${Math.min(current, 35)}%`;
    detailFontSize = 20;
  }

  return {
    tier,
    splitNumber,
    axisLabelDistance,
    detailOffsetCenterY,
    detailFontSize,
  };
}

/** Mirrors echarts GaugeView label placement relative to the arc outer radius. */
export function gaugeLabelInsetFromOuterEdge(
  axisLabelDistance: number,
  splitLineLength = 10,
  splitLineDistance = -16,
): number {
  return splitLineLength + axisLabelDistance + splitLineDistance;
}

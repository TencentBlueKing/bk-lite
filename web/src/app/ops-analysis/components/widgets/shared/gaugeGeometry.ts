import type { GaugeResponsiveLayout } from './gaugeResponsiveLayout';

export interface GaugeSeriesGeometry {
  radius: string;
  center: [string, string];
  fittedRadiusPx: number;
}

export interface GaugeGeometryFitInput {
  width: number;
  height: number;
  gaugeShape?: 'semicircle' | 'circle';
  desiredRadiusPercent: number;
  desiredCenterPercent: [number, number];
  axisLineWidth: number;
  layout: Pick<GaugeResponsiveLayout, 'detailOffsetCenterY' | 'detailFontSize'>;
}

const MIN_CIRCLE_CENTER_Y = 45;

function estimateDetailBottomPx(
  layout: Pick<GaugeResponsiveLayout, 'detailOffsetCenterY' | 'detailFontSize'>,
  radiusPx: number,
): number {
  const offsetRatio = Number.parseFloat(layout.detailOffsetCenterY) / 100;
  return offsetRatio * radiusPx + layout.detailFontSize * 0.65 + 6;
}

function toRadiusPercent(radiusPx: number, halfMin: number): string {
  if (halfMin <= 0) {
    return '100%';
  }
  const percent = Math.max(0, (radiusPx / halfMin) * 100);
  return `${percent}%`;
}

function fitCircleGeometry(input: GaugeGeometryFitInput): GaugeSeriesGeometry {
  const { width, height, desiredRadiusPercent, desiredCenterPercent, axisLineWidth, layout } =
    input;
  const halfMin = Math.min(width, height) / 2;
  const strokePad = axisLineWidth / 2 + 2;
  const centerX = desiredCenterPercent[0];
  let centerY = desiredCenterPercent[1];
  const desiredRadiusPx = (desiredRadiusPercent / 100) * halfMin;

  let cy = (centerY / 100) * height;
  const bottomReserve = estimateDetailBottomPx(layout, desiredRadiusPx);
  if (cy + bottomReserve > height - strokePad) {
    centerY = Math.max(
      MIN_CIRCLE_CENTER_Y,
      ((height - strokePad - bottomReserve) / height) * 100,
    );
    cy = (centerY / 100) * height;
  }

  const cx = (centerX / 100) * width;
  const maxRadius = Math.min(cx, width - cx, cy, height - cy) - strokePad;
  const fittedRadiusPx = Math.min(desiredRadiusPx, maxRadius);

  return {
    radius: toRadiusPercent(fittedRadiusPx, halfMin),
    center: [`${centerX}%`, `${centerY}%`],
    fittedRadiusPx,
  };
}

function fitSemicircleGeometry(input: GaugeGeometryFitInput): GaugeSeriesGeometry {
  const { width, height, desiredRadiusPercent, desiredCenterPercent, axisLineWidth, layout } =
    input;
  const halfMin = Math.min(width, height) / 2;
  const strokePad = axisLineWidth / 2 + 2;
  const topReserve = strokePad + 6;
  const centerX = desiredCenterPercent[0];
  let centerY = desiredCenterPercent[1];
  const desiredRadiusPx = (desiredRadiusPercent / 100) * halfMin;
  const cx = (centerX / 100) * width;
  const maxHorizontal = Math.min(cx, width - cx) - strokePad;

  let fittedRadiusPx = Math.min(desiredRadiusPx, maxHorizontal);
  for (let attempt = 0; attempt < 4; attempt += 1) {
    const bottomReserve = estimateDetailBottomPx(layout, fittedRadiusPx);
    const maxCenterY = ((height - strokePad - bottomReserve) / height) * 100;
    centerY = Math.min(desiredCenterPercent[1], maxCenterY);
    const cy = (centerY / 100) * height;
    const maxVertical = cy - topReserve;
    fittedRadiusPx = Math.min(desiredRadiusPx, maxHorizontal, maxVertical);

    if (cy + estimateDetailBottomPx(layout, fittedRadiusPx) <= height - strokePad) {
      break;
    }
  }

  const finalCy = (centerY / 100) * height;
  const bottomReserve = estimateDetailBottomPx(layout, fittedRadiusPx);
  if (finalCy + bottomReserve > height - strokePad) {
    centerY = Math.max(
      48,
      ((height - strokePad - bottomReserve) / height) * 100,
    );
    const cy = (centerY / 100) * height;
    fittedRadiusPx = Math.min(
      fittedRadiusPx,
      cy - topReserve,
      maxHorizontal,
    );
  }

  return {
    radius: toRadiusPercent(fittedRadiusPx, halfMin),
    center: [`${centerX}%`, `${centerY}%`],
    fittedRadiusPx,
  };
}

export function fitGaugeSeriesGeometry(input: GaugeGeometryFitInput): GaugeSeriesGeometry {
  if (input.width <= 0 || input.height <= 0) {
    return {
      radius: `${input.desiredRadiusPercent}%`,
      center: [`${input.desiredCenterPercent[0]}%`, `${input.desiredCenterPercent[1]}%`],
      fittedRadiusPx: 0,
    };
  }

  if (input.gaugeShape === 'circle') {
    return fitCircleGeometry(input);
  }

  return fitSemicircleGeometry(input);
}

/** Test helper: semicircle arc endpoints and detail must stay inside the chart box. */
export function semicircleGeometryFitsContainer(
  width: number,
  height: number,
  geometry: GaugeSeriesGeometry,
  axisLineWidth: number,
  layout: Pick<GaugeResponsiveLayout, 'detailOffsetCenterY' | 'detailFontSize'>,
): boolean {
  const strokePad = axisLineWidth / 2 + 2;
  const cx = (Number.parseFloat(geometry.center[0]) / 100) * width;
  const cy = (Number.parseFloat(geometry.center[1]) / 100) * height;
  const r = geometry.fittedRadiusPx;
  const bottom = cy + estimateDetailBottomPx(layout, r);

  return (
    cx - r >= strokePad
    && cx + r <= width - strokePad
    && cy - r >= strokePad
    && bottom <= height - strokePad
  );
}

/** Test helper: full circle must stay inside the chart box. */
export function circleGeometryFitsContainer(
  width: number,
  height: number,
  geometry: GaugeSeriesGeometry,
  axisLineWidth: number,
  layout: Pick<GaugeResponsiveLayout, 'detailOffsetCenterY' | 'detailFontSize'>,
): boolean {
  const strokePad = axisLineWidth / 2 + 2;
  const cx = (Number.parseFloat(geometry.center[0]) / 100) * width;
  const cy = (Number.parseFloat(geometry.center[1]) / 100) * height;
  const r = geometry.fittedRadiusPx;
  const bottom = cy + estimateDetailBottomPx(layout, r);

  return (
    cx - r >= strokePad
    && cx + r <= width - strokePad
    && cy - r >= strokePad
    && bottom <= height - strokePad
  );
}

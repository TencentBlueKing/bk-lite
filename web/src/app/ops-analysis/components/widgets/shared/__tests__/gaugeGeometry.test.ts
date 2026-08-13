import { describe, expect, it } from 'vitest';
import { getGaugeResponsiveLayout } from '../gaugeResponsiveLayout';
import {
  circleGeometryFitsContainer,
  fitGaugeSeriesGeometry,
  semicircleGeometryFitsContainer,
} from '../gaugeGeometry';

const semicircleLayout = (width: number, height: number) =>
  getGaugeResponsiveLayout({ width, height, gaugeShape: 'semicircle' });

const circleLayout = (width: number, height: number) =>
  getGaugeResponsiveLayout({ width, height, gaugeShape: 'circle' });

describe('gaugeGeometry', () => {
  it('keeps normal semicircle at desired radius when container is square and large', () => {
    const layout = semicircleLayout(320, 320);
    const geometry = fitGaugeSeriesGeometry({
      width: 320,
      height: 320,
      gaugeShape: 'semicircle',
      desiredRadiusPercent: 108,
      desiredCenterPercent: [50, 74],
      axisLineWidth: 14,
      layout,
    });

    expect(Number.parseFloat(geometry.radius)).toBeGreaterThan(90);
    expect(semicircleGeometryFitsContainer(320, 320, geometry, 14, layout)).toBe(true);
  });

  it('shrinks semicircle when width is constrained', () => {
    const layout = semicircleLayout(100, 320);
    const geometry = fitGaugeSeriesGeometry({
      width: 100,
      height: 320,
      gaugeShape: 'semicircle',
      desiredRadiusPercent: 108,
      desiredCenterPercent: [50, 74],
      axisLineWidth: 14,
      layout,
    });

    expect(geometry.fittedRadiusPx).toBeLessThan(54);
    expect(semicircleGeometryFitsContainer(100, 320, geometry, 14, layout)).toBe(true);
  });

  it('shrinks semicircle when height is constrained', () => {
    const layout = semicircleLayout(320, 100);
    const geometry = fitGaugeSeriesGeometry({
      width: 320,
      height: 100,
      gaugeShape: 'semicircle',
      desiredRadiusPercent: 108,
      desiredCenterPercent: [50, 74],
      axisLineWidth: 14,
      layout,
    });

    expect(geometry.fittedRadiusPx).toBeLessThan(54);
    expect(semicircleGeometryFitsContainer(320, 100, geometry, 14, layout)).toBe(true);
  });

  it('fits semicircle for common widget sizes without exceeding safe bounds', () => {
    const sizes = [
      [120, 120],
      [180, 180],
      [320, 320],
      [320, 100],
      [100, 320],
    ] as const;

    sizes.forEach(([width, height]) => {
      const layout = semicircleLayout(width, height);
      const geometry = fitGaugeSeriesGeometry({
        width,
        height,
        gaugeShape: 'semicircle',
        desiredRadiusPercent: 108,
        desiredCenterPercent: [50, 74],
        axisLineWidth: 14,
        layout,
      });

      expect(semicircleGeometryFitsContainer(width, height, geometry, 14, layout)).toBe(true);
    });
  });

  it('keeps full circle geometry safe without over-shrinking on square containers', () => {
    const layout = circleLayout(320, 320);
    const geometry = fitGaugeSeriesGeometry({
      width: 320,
      height: 320,
      gaugeShape: 'circle',
      desiredRadiusPercent: 90,
      desiredCenterPercent: [50, 56],
      axisLineWidth: 14,
      layout,
    });

    expect(Number.parseFloat(geometry.radius)).toBeGreaterThan(80);
    expect(circleGeometryFitsContainer(320, 320, geometry, 14, layout)).toBe(true);
  });
});

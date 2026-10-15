import { describe, expect, it } from 'vitest';
import {
  applicationTopologyChromeScale,
  applicationTopologyLabelRailWidth,
  clampApplicationTopologyScale,
  fitApplicationTopologyLayers,
  zoomApplicationTopologyAt,
} from '../viewport';

describe('application topology viewport', () => {
  it('enlarges a narrow cluster in the center and keeps every layer in view', () => {
    const view = fitApplicationTopologyLayers({
      viewportWidth: 1600,
      viewportHeight: 720,
      clusterX: 640,
      clusterWidth: 480,
      layerHeight: 540,
    });
    expect(view.scale).toBeGreaterThan(1);
    const clusterLeft = view.x + 640 * view.scale;
    const clusterRight = clusterLeft + 480 * view.scale;
    expect((clusterLeft + clusterRight) / 2).toBeCloseTo(800, 0);
    expect(clusterLeft).toBeGreaterThan(80);
    expect(view.y).toBeGreaterThanOrEqual(0);
    expect(view.y + 540 * view.scale).toBeLessThanOrEqual(720 + 0.01);
  });

  it('reserves the same label rail on both sides and centers the cluster', () => {
    const rail = 96;
    const gap = 10;
    const view = fitApplicationTopologyLayers({
      viewportWidth: 1600,
      viewportHeight: 720,
      clusterX: 640,
      clusterWidth: 480,
      layerHeight: 540,
      labelRailWidth: rail,
      labelGap: gap,
    });
    const clusterLeft = view.x + 640 * view.scale;
    const clusterRight = clusterLeft + 480 * view.scale;
    expect((clusterLeft + clusterRight) / 2).toBeCloseTo(800, 0);
    expect(clusterLeft).toBeCloseTo(1600 - clusterRight, 0);
    expect(clusterLeft).toBeGreaterThanOrEqual(rail + gap);
  });

  it('shrinks a taller layer stack so the last band stays in view', () => {
    const view = fitApplicationTopologyLayers({
      viewportWidth: 800,
      viewportHeight: 320,
      clusterX: 0,
      clusterWidth: 800,
      layerHeight: 900,
    });
    expect(view.scale).toBeLessThan(1);
    expect(view.y).toBeGreaterThanOrEqual(0);
    expect(view.y + 900 * view.scale).toBeLessThanOrEqual(320 + 0.01);
    const clusterCenter = view.x + 400 * view.scale;
    expect(clusterCenter).toBeCloseTo(400, 0);
  });

  it('zooms toward the pointer', () => {
    const next = zoomApplicationTopologyAt({
      scale: 1,
      x: 0,
      y: 0,
      pointerX: 100,
      pointerY: 40,
      nextScale: 2,
    });
    expect(next.scale).toBe(2);
    expect(next.x).toBe(-100);
    expect(next.y).toBe(-40);
  });

  it('sizes layer labels with the graph scale, same as node titles', () => {
    expect(applicationTopologyChromeScale(1)).toBe(1);
    expect(applicationTopologyChromeScale(0.4)).toBe(0.4);
    expect(applicationTopologyChromeScale(2)).toBe(2);
    expect(applicationTopologyLabelRailWidth(1)).toBe(168);
    expect(applicationTopologyLabelRailWidth(2)).toBeGreaterThan(168);
    expect(applicationTopologyLabelRailWidth(0.4)).toBe(112);
  });

  it('clamps the scale', () => {
    expect(clampApplicationTopologyScale(8)).toBe(2.5);
    expect(clampApplicationTopologyScale(0.01)).toBe(0.25);
  });
});

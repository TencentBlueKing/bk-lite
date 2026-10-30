import { describe, expect, it } from 'vitest';
import { scaleScreenMetric } from '@/app/ops-analysis/components/widgets/shared/screenMetrics';
import { resolveCanvasContentScale } from '@/app/ops-analysis/utils/interactionMenuScale';
import {
  calculateScreenFitMetrics,
  calculateScreenVisualMetrics,
  mapDesignBoxToViewportPixels,
  presentScreenRenderContext,
  resolveChromeFontDensity,
  scalePresentedFontPx,
} from '../metrics';

describe('calculateScreenFitMetrics adapters', () => {
  it('fill stretches each axis to the window and does not scroll', () => {
    const fit = calculateScreenFitMetrics({
      contentWidth: 1920,
      contentHeight: 1200,
      designWidth: 1920,
      designHeight: 1080,
      adapter: 'fill',
    });

    expect(fit.scaleX).toBe(1);
    expect(fit.scaleY).toBeCloseTo(1200 / 1080);
    expect(fit.renderedWidth).toBe(1920);
    expect(fit.renderedHeight).toBe(1200);
    expect(fit.overflowX).toBe(false);
    expect(fit.overflowY).toBe(false);
  });

  it('contain letterboxes a taller screen without scrolling', () => {
    const fit = calculateScreenFitMetrics({
      contentWidth: 1920,
      contentHeight: 1200,
      designWidth: 1920,
      designHeight: 1080,
      adapter: 'contain',
    });

    expect(fit.scaleX).toBe(1);
    expect(fit.scaleY).toBe(1);
    expect(fit.renderedWidth).toBe(1920);
    expect(fit.renderedHeight).toBe(1080);
    expect(fit.overflowX).toBe(false);
    expect(fit.overflowY).toBe(false);
  });

  it('fitWidth on a taller screen matches the width and leaves vertical space', () => {
    const fit = calculateScreenFitMetrics({
      contentWidth: 1920,
      contentHeight: 1200,
      designWidth: 1920,
      designHeight: 1080,
      adapter: 'fitWidth',
    });

    expect(fit.scaleX).toBe(1);
    expect(fit.scaleY).toBe(1);
    expect(fit.overflowX).toBe(false);
    expect(fit.overflowY).toBe(false);
  });

  it('fitHeight on a taller screen scales uniformly and scrolls sideways', () => {
    const fit = calculateScreenFitMetrics({
      contentWidth: 1920,
      contentHeight: 1200,
      designWidth: 1920,
      designHeight: 1080,
      adapter: 'fitHeight',
    });

    expect(fit.scaleX).toBeCloseTo(1200 / 1080);
    expect(fit.scaleY).toBeCloseTo(1200 / 1080);
    expect(fit.renderedHeight).toBe(1200);
    expect(fit.renderedWidth).toBe(Math.round(1920 * (1200 / 1080)));
    expect(fit.overflowX).toBe(true);
    expect(fit.overflowY).toBe(false);
  });

  it('fitWidth on an ultrawide screen scales uniformly and scrolls vertically', () => {
    const fit = calculateScreenFitMetrics({
      contentWidth: 2560,
      contentHeight: 1080,
      designWidth: 1920,
      designHeight: 1080,
      adapter: 'fitWidth',
    });

    expect(fit.scaleX).toBeCloseTo(2560 / 1920);
    expect(fit.scaleY).toBeCloseTo(2560 / 1920);
    expect(fit.renderedWidth).toBe(2560);
    expect(fit.overflowX).toBe(false);
    expect(fit.overflowY).toBe(true);
  });

  it('defaults missing adapter to fill', () => {
    const withDefault = calculateScreenFitMetrics({
      contentWidth: 1920,
      contentHeight: 1200,
      designWidth: 1920,
      designHeight: 1080,
    });
    const fill = calculateScreenFitMetrics({
      contentWidth: 1920,
      contentHeight: 1200,
      designWidth: 1920,
      designHeight: 1080,
      adapter: 'fill',
    });

    expect(withDefault).toEqual(fill);
  });
});

describe('viewport pixel font scale', () => {
  // 2304×1400 对 1920×1080：sx=1.2，sy=1400/1080，几何密度取 min=1.2。
  // 字号用 screenDensity。再乘 fitScale 或沿用 screenUiScale 都会偏离屏幕结果。
  const visual = calculateScreenVisualMetrics({
    contentWidth: 2304,
    contentHeight: 1400,
    designWidth: 1920,
    designHeight: 1080,
    adapter: 'fill',
  });

  it('keeps independent fill axis scales', () => {
    expect(visual.scaleX).toBeCloseTo(1.2);
    expect(visual.scaleY).toBeCloseTo(1400 / 1080);
    expect(visual.fitScale).toBeCloseTo(1.2);
  });

  it('sizes fullscreen fill text by screen density once', () => {
    const presented = presentScreenRenderContext({
      layoutMode: 'viewportPixels',
      fitScale: visual.fitScale,
      scaleX: visual.scaleX,
      scaleY: visual.scaleY,
      screenDensity: visual.screenDensity,
      transformUiScale: visual.screenUiScale,
    });

    expect(presented.context.layoutMode).toBe('viewportPixels');
    expect(presented.context.scaleX).toBeCloseTo(1.2);
    expect(presented.context.widgetUiScale).toBeCloseTo(visual.screenDensity);
    expect(presented.widgetViewportScale).toBe(1);
    expect(scaleScreenMetric(20, presented.context)).toBe(
      Math.round(20 * visual.screenDensity),
    );
    expect(scalePresentedFontPx(20, presented.context.widgetUiScale)).toBe(
      Math.round(20 * visual.screenDensity),
    );
    expect(scaleScreenMetric(20, presented.context)).not.toBe(19);
    expect(scaleScreenMetric(20, presented.context)).not.toBe(24);
    expect(scaleScreenMetric(20, presented.context)).not.toBe(29);
    expect(resolveCanvasContentScale(presented.context)).toBe(1);
  });

  it('does not shrink 4K chart text down to fitScale on a 1080p viewport', () => {
    const fitted = calculateScreenVisualMetrics({
      contentWidth: 1920,
      contentHeight: 1080,
      designWidth: 3840,
      designHeight: 2160,
      adapter: 'fill',
    });
    const presented = presentScreenRenderContext({
      layoutMode: 'viewportPixels',
      fitScale: fitted.fitScale,
      scaleX: fitted.scaleX,
      scaleY: fitted.scaleY,
      screenDensity: fitted.screenDensity,
      transformUiScale: fitted.screenUiScale,
    });

    expect(fitted.fitScale).toBeCloseTo(0.5);
    expect(presented.context.widgetUiScale).toBeCloseTo(fitted.screenDensity);
    expect(presented.context.widgetUiScale).toBeGreaterThan(1);
    expect(scaleScreenMetric(24, presented.context)).toBe(
      Math.round(24 * fitted.screenDensity),
    );
    expect(scaleScreenMetric(24, presented.context)).not.toBe(12);
    expect(scaleScreenMetric(24, presented.context)).not.toBe(24);
    expect(scaleScreenMetric(24, presented.context)).not.toBe(
      Math.round(24 * fitted.screenUiScale),
    );
  });

  it('keeps the transform-path ui scale when layout stays on the design canvas', () => {
    const presented = presentScreenRenderContext({
      layoutMode: 'designTransform',
      fitScale: visual.fitScale,
      scaleX: visual.scaleX,
      scaleY: visual.scaleY,
      screenDensity: visual.screenDensity,
      transformUiScale: visual.screenUiScale,
    });

    expect(presented.context.layoutMode).toBe('designTransform');
    expect(presented.context.widgetUiScale).toBeCloseTo(visual.screenUiScale);
    expect(presented.widgetViewportScale).toBeCloseTo(visual.fitScale);
    expect(resolveCanvasContentScale(presented.context)).toBeCloseTo(1.2);
  });
});

describe('viewport pixel chrome title and clock', () => {
  it('scales the hero title and clock by fitScale, not screenDensity', () => {
    const fitted = calculateScreenVisualMetrics({
      contentWidth: 1920,
      contentHeight: 1080,
      designWidth: 3840,
      designHeight: 2160,
      adapter: 'fill',
    });
    const density = resolveChromeFontDensity('viewportPixels', fitted.fitScale);
    const chart = presentScreenRenderContext({
      layoutMode: 'viewportPixels',
      fitScale: fitted.fitScale,
      scaleX: fitted.scaleX,
      scaleY: fitted.scaleY,
      screenDensity: fitted.screenDensity,
      transformUiScale: fitted.screenUiScale,
    });

    expect(density).toBeCloseTo(0.5);
    expect(scalePresentedFontPx(56, density)).toBe(28);
    expect(scalePresentedFontPx(34, density)).toBe(17);
    expect(scalePresentedFontPx(56, density)).not.toBe(56);
    expect(scalePresentedFontPx(56, density)).not.toBe(
      scalePresentedFontPx(56, fitted.screenDensity),
    );
    expect(chart.context.widgetUiScale).toBeCloseTo(fitted.screenDensity);
    expect(scaleScreenMetric(24, chart.context)).not.toBe(scalePresentedFontPx(24, density));
  });

  it('leaves edit, view, and PDF chrome fonts at design pixels', () => {
    expect(resolveChromeFontDensity('designTransform', 0.5)).toBe(1);
    expect(scalePresentedFontPx(56, resolveChromeFontDensity('designTransform', 0.5))).toBe(56);
    expect(scalePresentedFontPx(34, resolveChromeFontDensity('designTransform', 1.2))).toBe(34);
  });
});

describe('mapDesignBoxToViewportPixels', () => {
  it('maps each axis independently and does not mutate the design box', () => {
    const design = { x: 10, y: 10, w: 30, h: 20 };
    const mapped = mapDesignBoxToViewportPixels(design, 1, 1200 / 1080);

    expect(mapped).toEqual({ x: 10, y: 11, w: 30, h: 22 });
    expect(design).toEqual({ x: 10, y: 10, w: 30, h: 20 });
  });

  it('keeps a zero-width design box at least one pixel', () => {
    expect(mapDesignBoxToViewportPixels({ x: 0, y: 0, w: 0, h: 0 }, 2, 2)).toEqual({
      x: 0,
      y: 0,
      w: 1,
      h: 1,
    });
  });
});

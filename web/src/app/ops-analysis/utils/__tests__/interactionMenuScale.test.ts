import { describe, expect, it } from 'vitest';

import {
  INTERACTION_MENU_FONT_FLOOR_PX,
  INTERACTION_MENU_FONT_PX,
  INTERACTION_MENU_SCALE_MAX,
  INTERACTION_MENU_SCALE_MIN,
  resolveInteractionMenuScale,
  resolvePortaledMenuScale,
} from '@/app/ops-analysis/utils/interactionMenuScale';

const screen = (
  overrides: Partial<Parameters<typeof resolveInteractionMenuScale>[0]> = {},
) => ({
  enabled: true,
  fitScale: 1,
  scaleX: 1,
  scaleY: 1,
  screenDensity: 1,
  screenUiScale: 1,
  widgetDensity: 1,
  widgetUiScale: 1,
  ...overrides,
});

describe('interaction menu scale', () => {
  it('stays at 1 outside a big screen', () => {
    expect(resolveInteractionMenuScale(null)).toBe(1);
    expect(resolveInteractionMenuScale(undefined)).toBe(1);
    expect(resolveInteractionMenuScale(screen({
      enabled: false,
      fitScale: 0.4,
      scaleX: 0.4,
      scaleY: 0.4,
      widgetUiScale: 0.5,
    }))).toBe(1);
  });

  it('does not raise a scale between the font floor and 1', () => {
    expect(resolveInteractionMenuScale(screen({
      fitScale: 0.9,
      scaleX: 0.9,
      scaleY: 0.9,
      widgetUiScale: 1,
    }))).toBe(0.9);
  });

  it('keeps a 12px font at or above 10px', () => {
    const scale = resolveInteractionMenuScale(screen({
      fitScale: 0.4,
      scaleX: 0.4,
      scaleY: 0.4,
      widgetUiScale: 1,
    }));
    expect(scale).toBeCloseTo(INTERACTION_MENU_SCALE_MIN, 5);
    expect(INTERACTION_MENU_FONT_PX * scale).toBeGreaterThanOrEqual(INTERACTION_MENU_FONT_FLOOR_PX);
  });

  it('caps a canvas scale above 1.6', () => {
    expect(resolveInteractionMenuScale(screen({
      fitScale: 2,
      scaleX: 2,
      scaleY: 2,
      widgetUiScale: 1.2,
    }))).toBe(INTERACTION_MENU_SCALE_MAX);
  });

  it('multiplies the uniform canvas scale by the widget ui scale', () => {
    expect(resolveInteractionMenuScale(screen({
      fitScale: 1,
      scaleX: 1.25,
      scaleY: 1.25,
      widgetUiScale: 1.2,
      screenUiScale: 2,
    }))).toBe(1.5);
  });

  it('uses fitScale when the canvas is stretched on both axes', () => {
    expect(resolveInteractionMenuScale(screen({
      fitScale: 1.25,
      scaleX: 2,
      scaleY: 1,
      widgetUiScale: 1,
    }))).toBe(1.25);
  });

  it('matches a room3D card by multiplying its in-canvas scale by the canvas scale', () => {
    const shrunk = screen({ fitScale: 0.6, scaleX: 0.6, scaleY: 0.6, widgetUiScale: 1 });
    expect(resolvePortaledMenuScale(1 / 0.6, shrunk)).toBe(1);

    const enlarged = screen({ fitScale: 1.5, scaleX: 1.5, scaleY: 1.5, widgetUiScale: 1 });
    expect(resolvePortaledMenuScale(1, enlarged)).toBe(1.5);

    expect(resolvePortaledMenuScale(1.2, screen({
      fitScale: 2,
      scaleX: 2,
      scaleY: 2,
    }))).toBe(INTERACTION_MENU_SCALE_MAX);

    expect(resolvePortaledMenuScale(2, screen({ enabled: false, fitScale: 0.6 }))).toBe(1);
  });
});

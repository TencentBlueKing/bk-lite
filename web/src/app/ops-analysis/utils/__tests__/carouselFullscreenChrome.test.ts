import { describe, expect, it } from 'vitest';
import {
  CAROUSEL_FULLSCREEN_CHROME,
  CAROUSEL_FULLSCREEN_CONTROLS_IDLE_MS,
  CAROUSEL_FULLSCREEN_EXIT_TIP_MS,
  CAROUSEL_FULLSCREEN_RESUME_HINT_MS,
  CAROUSEL_FULLSCREEN_SEGMENT_MAX,
  carouselDwellFill,
  fullscreenStageCursor,
  markFullscreenExitTipSeen,
  planFullscreenChrome,
  readFullscreenExitTipSeen,
  resolveCarouselFullscreenProgress,
} from '@/app/ops-analysis/utils/carouselFullscreenChrome';

const slides = (count: number, unavailableAt: number[] = []) => (
  Array.from({ length: count }, (_, index) => ({
    available: !unavailableAt.includes(index),
    dwellSeconds: 30,
  }))
);

const memoryStorage = () => {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value);
    },
  };
};

describe('carousel fullscreen chrome', () => {
  it('splits progress into segments through 20 canvases and switches to one bar after that', () => {
    const atLimit = resolveCarouselFullscreenProgress({
      slides: slides(CAROUSEL_FULLSCREEN_SEGMENT_MAX),
      index: 2,
      remainingMs: 15_000,
      paused: false,
    });
    expect(atLimit.mode).toBe('segments');
    expect(atLimit.segments).toHaveLength(20);
    expect(atLimit.segments[0]).toEqual({ tone: 'played', fill: 1 });
    expect(atLimit.segments[1]).toEqual({ tone: 'played', fill: 1 });
    expect(atLimit.segments[2]).toEqual({ tone: 'current', fill: 0.5 });
    expect(atLimit.segments[3]).toEqual({ tone: 'upcoming', fill: 0 });
    expect(atLimit.currentColor).toBe(CAROUSEL_FULLSCREEN_CHROME.current);

    const continuous = resolveCarouselFullscreenProgress({
      slides: slides(CAROUSEL_FULLSCREEN_SEGMENT_MAX + 1),
      index: 2,
      remainingMs: 15_000,
      paused: false,
    });
    expect(continuous.mode).toBe('continuous');
    expect(continuous.continuous).toBeCloseTo(2.5 / 21);
  });

  it('marks unavailable canvases and freezes the current color while paused', () => {
    const playing = resolveCarouselFullscreenProgress({
      slides: slides(4, [1]),
      index: 2,
      remainingMs: 6_000,
      paused: false,
    });
    const paused = resolveCarouselFullscreenProgress({
      slides: slides(4, [1]),
      index: 2,
      remainingMs: 6_000,
      paused: true,
    });
    expect(playing.segments.map((segment) => segment.tone)).toEqual([
      'played',
      'unavailable',
      'current',
      'upcoming',
    ]);
    expect(playing.segments[2].fill).toBeCloseTo(carouselDwellFill(30, 6_000));
    expect(paused.segments[2].fill).toBe(playing.segments[2].fill);
    expect(paused.currentColor).toBe(CAROUSEL_FULLSCREEN_CHROME.paused);
    expect(paused.continuous).toBeCloseTo((2 + playing.segments[2].fill) / 4);
  });

  it('keeps a hold at index -1 empty instead of filling the first canvas', () => {
    const held = resolveCarouselFullscreenProgress({
      slides: slides(4, [0, 1, 2, 3]),
      index: -1,
      remainingMs: 0,
      paused: false,
    });
    expect(held.segments).toEqual([
      { tone: 'unavailable', fill: 0 },
      { tone: 'unavailable', fill: 0 },
      { tone: 'unavailable', fill: 0 },
      { tone: 'unavailable', fill: 0 },
    ]);
    expect(held.continuous).toBe(0);
    expect(held.segments.some((segment) => segment.tone === 'current' || segment.tone === 'played')).toBe(false);

    const continuous = resolveCarouselFullscreenProgress({
      slides: slides(CAROUSEL_FULLSCREEN_SEGMENT_MAX + 1),
      index: -1,
      remainingMs: 0,
      paused: false,
    });
    expect(continuous.mode).toBe('continuous');
    expect(continuous.continuous).toBe(0);
    expect(continuous.segments.some((segment) => segment.tone === 'current')).toBe(false);
  });

  it('keeps the corner cluster up while paused or hovered, and hides it shortly after the pointer leaves', () => {
    const playing = { paused: false, hoveringHotzone: false };
    const hovering = { paused: false, hoveringHotzone: true };
    const paused = { paused: true, hoveringHotzone: false };
    expect(CAROUSEL_FULLSCREEN_CONTROLS_IDLE_MS).toBe(500);
    expect(CAROUSEL_FULLSCREEN_RESUME_HINT_MS).toBe(2000);
    expect(CAROUSEL_FULLSCREEN_EXIT_TIP_MS).toBe(2500);
    expect(CAROUSEL_FULLSCREEN_CHROME.border).toBe('rgba(103, 232, 249, 0.55)');
    expect(CAROUSEL_FULLSCREEN_CHROME).not.toHaveProperty('playSurface');
    expect(CAROUSEL_FULLSCREEN_CHROME).not.toHaveProperty('shade');

    expect(planFullscreenChrome('resumed', playing)).toEqual({ visible: false, armIdleTimer: false });
    expect(planFullscreenChrome('hotzone-enter', hovering)).toEqual({ visible: true, armIdleTimer: false });
    expect(planFullscreenChrome('hotzone-leave', playing)).toEqual({ visible: true, armIdleTimer: true });
    expect(planFullscreenChrome('hide-elapsed', playing)).toEqual({ visible: false, armIdleTimer: false });
    expect(planFullscreenChrome('hide-elapsed', hovering)).toEqual({ visible: true, armIdleTimer: false });
    expect(planFullscreenChrome('paused', paused)).toEqual({ visible: true, armIdleTimer: false });
    expect(planFullscreenChrome('hotzone-leave', paused)).toEqual({ visible: true, armIdleTimer: false });
    expect(planFullscreenChrome('hide-elapsed', paused)).toEqual({ visible: true, armIdleTimer: false });
    expect(planFullscreenChrome('resumed', hovering)).toEqual({ visible: true, armIdleTimer: false });
    expect(fullscreenStageCursor()).toBe('auto');
  });

  it('shows the Esc tip once per browser tab', () => {
    const storage = memoryStorage();
    expect(readFullscreenExitTipSeen(null)).toBe(false);
    expect(readFullscreenExitTipSeen(storage)).toBe(false);
    markFullscreenExitTipSeen(null);
    markFullscreenExitTipSeen(storage);
    expect(readFullscreenExitTipSeen(storage)).toBe(true);
  });
});

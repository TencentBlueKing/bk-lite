import { describe, expect, it } from 'vitest';
import {
  CAROUSEL_UNAVAILABLE_RETRY_MS,
  carouselHiddenGroupIds,
  clampCarouselDwellSeconds,
  createCarouselPlayerState,
  isCarouselBusinessFailure,
  isCarouselHotkeyBlocked,
  reduceCarouselLoad,
  reduceCarouselPlayer,
  skippedCarouselCount,
  type CarouselSlideInput,
} from '@/app/ops-analysis/utils/carouselPlayer';

const slides = (available: boolean[]): CarouselSlideInput[] =>
  available.map((isAvailable, index) => ({
    key: `s${index}`,
    available: isAvailable,
    dwellSeconds: index === 1 ? 10 : 30,
  }));

describe('carousel player', () => {
  it('starts on the first available slide and resolves dwell', () => {
    const state = createCarouselPlayerState(slides([false, true, true]));
    expect(state.index).toBe(1);
    expect(state.remainingMs).toBe(10_000);
    expect(skippedCarouselCount(state)).toBe(1);
    expect(clampCarouselDwellSeconds(4)).toBe(5);
    expect(clampCarouselDwellSeconds(301)).toBe(300);
    expect(clampCarouselDwellSeconds('nope')).toBe(30);
  });

  it('ticks down, pauses, and loops back to the first available slide', () => {
    let state = createCarouselPlayerState(slides([true, false, true]));
    state = reduceCarouselPlayer(state, { type: 'tick', deltaMs: 1000 });
    expect(state.index).toBe(0);
    expect(state.remainingMs).toBe(29_000);

    state = reduceCarouselPlayer(state, { type: 'togglePause' });
    const paused = reduceCarouselPlayer(state, { type: 'tick', deltaMs: 50_000 });
    expect(paused.index).toBe(0);
    expect(paused.remainingMs).toBe(29_000);

    state = reduceCarouselPlayer(paused, { type: 'togglePause' });
    state = reduceCarouselPlayer(state, { type: 'tick', deltaMs: 29_000 });
    expect(state.index).toBe(2);
    expect(state.remainingMs).toBe(30_000);

    state = reduceCarouselPlayer(state, { type: 'tick', deltaMs: 30_000 });
    expect(state.index).toBe(0);
    expect(state.visit).toBeGreaterThan(0);
  });

  it('manual next and previous skip unavailable slides and wrap', () => {
    let state = createCarouselPlayerState(slides([true, false, true]));
    state = reduceCarouselPlayer(state, { type: 'next' });
    expect(state.index).toBe(2);
    state = reduceCarouselPlayer(state, { type: 'next' });
    expect(state.index).toBe(0);
    state = reduceCarouselPlayer(state, { type: 'prev' });
    expect(state.index).toBe(2);
  });

  it('a single slide loops onto itself and a failed slide is skipped', () => {
    let state = createCarouselPlayerState(slides([true]));
    const looped = reduceCarouselPlayer(state, { type: 'next' });
    expect(looped.index).toBe(0);
    expect(looped.visit).toBe(state.visit + 1);
    expect(looped.remainingMs).toBe(30_000);

    state = createCarouselPlayerState(slides([true, true]));
    state = reduceCarouselPlayer(state, { type: 'markUnavailable', key: 's0' });
    expect(state.index).toBe(1);
    expect(skippedCarouselCount(state)).toBe(1);

    state = reduceCarouselPlayer(state, { type: 'markUnavailable', key: 's1' });
    expect(state.index).toBe(-1);
    expect(skippedCarouselCount(state)).toBe(2);
  });

  it('can rest on an unavailable slide and skips it as soon as playback resumes', () => {
    let state = createCarouselPlayerState(slides([true, false, true]));
    state = reduceCarouselPlayer(state, { type: 'selectIndex', index: 1 });
    expect(state.index).toBe(1);
    state = reduceCarouselPlayer(state, { type: 'setPaused', paused: true });
    const held = reduceCarouselPlayer(state, { type: 'tick', deltaMs: 10_000 });
    expect(held.index).toBe(1);
    state = reduceCarouselPlayer(held, { type: 'setPaused', paused: false });
    state = reduceCarouselPlayer(state, { type: 'tick', deltaMs: 1 });
    expect(state.index).toBe(2);
  });

  it('keeps the current slide when the playlist is refreshed', () => {
    const current = createCarouselPlayerState(slides([true, true]));
    const moved = reduceCarouselPlayer(current, { type: 'next' });
    const reset = reduceCarouselPlayer(moved, {
      type: 'reset',
      slides: slides([false, true]),
      preferKey: 's1',
    });
    expect(reset.index).toBe(1);
    expect(reset.paused).toBe(false);
  });

  it('compares canvas groups against the carousel groups', () => {
    expect(carouselHiddenGroupIds([1, 3], [1, 2, 3])).toEqual([2]);
    expect(carouselHiddenGroupIds([], [1])).toEqual([1]);
  });

  it('retries a slide after a transient prefetch failure, and skips it only if enter also fails', () => {
    let state = createCarouselPlayerState(slides([true, true]));
    state = reduceCarouselLoad(state, {
      key: 's1',
      phase: 'prefetch',
      ok: false,
      business: isCarouselBusinessFailure(new Error('network')),
    });
    expect(state.index).toBe(0);
    expect(state.slides[1].available).toBe(true);

    state = reduceCarouselLoad(state, { key: 's1', phase: 'enter', ok: true });
    expect(state.slides[1].available).toBe(true);

    state = reduceCarouselPlayer(state, { type: 'next' });
    state = reduceCarouselLoad(state, {
      key: 's1',
      phase: 'enter',
      ok: false,
      business: false,
    });
    expect(state.index).toBe(0);
    expect(state.slides[1].available).toBe(false);
    expect(skippedCarouselCount(state)).toBe(1);
  });

  it('skips a business failure for this lap and checks it again next lap', () => {
    let state = createCarouselPlayerState(slides([true, true]));
    state = reduceCarouselLoad(state, {
      key: 's0',
      phase: 'prefetch',
      ok: false,
      business: isCarouselBusinessFailure({ status: 404 }),
    });
    expect(state.index).toBe(1);
    expect(state.slides[0].available).toBe(false);
    expect(isCarouselBusinessFailure({ status: 403 })).toBe(true);
    expect(isCarouselBusinessFailure({ status: 500 })).toBe(false);

    state = reduceCarouselPlayer(state, { type: 'tick', deltaMs: 10_000 });
    expect(state.slides[0].available).toBe(true);
    expect(state.index).toBe(0);
    expect(state.slides.every((slide) => slide.available)).toBe(true);
  });

  it('waits before retrying when every slide is unavailable', () => {
    let state = createCarouselPlayerState(slides([false, false]));
    expect(state.index).toBe(-1);
    expect(state.holdMs).toBe(CAROUSEL_UNAVAILABLE_RETRY_MS);

    state = reduceCarouselPlayer(state, { type: 'tick', deltaMs: 1_000 });
    expect(state.index).toBe(-1);
    expect(state.holdMs).toBe(CAROUSEL_UNAVAILABLE_RETRY_MS - 1_000);

    state = createCarouselPlayerState(slides([true]));
    state = reduceCarouselLoad(state, {
      key: 's0',
      phase: 'enter',
      ok: false,
      business: true,
    });
    expect(state.index).toBe(-1);
    expect(state.holdMs).toBe(CAROUSEL_UNAVAILABLE_RETRY_MS);
    state = reduceCarouselPlayer(state, { type: 'tick', deltaMs: 250 });
    expect(state.index).toBe(-1);

    state = reduceCarouselPlayer(state, { type: 'tick', deltaMs: CAROUSEL_UNAVAILABLE_RETRY_MS });
    expect(state.index).toBe(0);
    expect(state.slides[0].available).toBe(true);
    expect(state.holdMs).toBe(0);
  });

  it('ignores hotkeys from inputs and open selectors', () => {
    const input = document.createElement('input');
    const button = document.createElement('button');
    const picker = document.createElement('div');
    picker.className = 'ant-select';
    const option = document.createElement('span');
    picker.append(option);
    expect(isCarouselHotkeyBlocked(input)).toBe(true);
    expect(isCarouselHotkeyBlocked(button)).toBe(false);
    expect(isCarouselHotkeyBlocked(option)).toBe(true);
  });
});

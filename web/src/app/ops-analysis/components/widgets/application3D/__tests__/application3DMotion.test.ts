import { describe, expect, it } from 'vitest';
import {
  WALL_ENTRANCE,
  cardStaggerDelayMs,
  easeOutEntrance,
  wallEntranceSpanMs,
} from '../application3DMotion';

describe('application3D wall entrance motion', () => {
  it('staggers left-to-right without exceeding the max delay', () => {
    expect(cardStaggerDelayMs(0, 12)).toBe(0);
    expect(cardStaggerDelayMs(1, 8)).toBe(WALL_ENTRANCE.staggerMs);
    expect(cardStaggerDelayMs(11, 12)).toBeLessThanOrEqual(WALL_ENTRANCE.maxStaggerMs);
  });

  it('compresses stagger when the wall is dense', () => {
    const denseLast = cardStaggerDelayMs(199, 200);
    const regularStep = cardStaggerDelayMs(1, 8);
    expect(denseLast).toBeLessThanOrEqual(WALL_ENTRANCE.maxStaggerMs);
    expect(cardStaggerDelayMs(1, 200)).toBeLessThan(regularStep);
  });

  it('keeps the full entrance under 900ms', () => {
    expect(wallEntranceSpanMs(1)).toBeLessThanOrEqual(900);
    expect(wallEntranceSpanMs(12)).toBeLessThanOrEqual(900);
    expect(wallEntranceSpanMs(200)).toBeLessThanOrEqual(900);
    expect(wallEntranceSpanMs(200)).toBe(
      WALL_ENTRANCE.cardStartMs + WALL_ENTRANCE.maxStaggerMs + WALL_ENTRANCE.cardDurationMs,
    );
  });

  it('uses a decelerating ease-out without bounce', () => {
    expect(easeOutEntrance(0)).toBe(0);
    expect(easeOutEntrance(1)).toBe(1);
    expect(easeOutEntrance(0.35)).toBeGreaterThan(0.35);
    expect(easeOutEntrance(0.85)).toBeGreaterThan(0.85);
    expect(easeOutEntrance(1.2)).toBe(1);
  });
});

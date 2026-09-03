import { describe, expect, it } from 'vitest';
import {
  WALL_ENTRANCE,
  ARCHITECTURE_MOTION,
  architectureLabelDelayMs,
  architectureNodeDelayMs,
  architecturePlaneDelayMs,
  architecturePlanesDoneMs,
  architectureTubeDelayMs,
  cardStaggerDelayMs,
  easeLinear,
  easeOutEntrance,
  wallEntranceSpanMs,
} from '../application3DMotion';
import { durationFromSpeed, easeInOutCubic } from '../application3DVisual';

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

  it('flies the architecture camera for about 3s cubic ease-in-out before expand', () => {
    expect(ARCHITECTURE_MOTION.cameraMs).toBeGreaterThanOrEqual(2800);
    expect(ARCHITECTURE_MOTION.cameraMs).toBeLessThanOrEqual(3200);
    expect(ARCHITECTURE_MOTION.cameraMs).toBe(Math.round(durationFromSpeed(100 / 60 / 3) * 1000));
    expect('cameraBetaDelta' in ARCHITECTURE_MOTION).toBe(false);
    expect(ARCHITECTURE_MOTION.cameraRadiusScale).toBe(1);
    expect(ARCHITECTURE_MOTION.cameraTargetLift).toBeLessThan(0);
    expect(ARCHITECTURE_MOTION.cameraTargetLift).toBeGreaterThan(-1);
    expect(ARCHITECTURE_MOTION.cameraTargetForward).toBe(0);
    expect(ARCHITECTURE_MOTION.planeStartDistance).toBeGreaterThanOrEqual(10);
    expect(ARCHITECTURE_MOTION.wallHideMs).toBe(500);
    expect(ARCHITECTURE_MOTION.wallHideScale).toBeLessThan(0.5);
    expect(ARCHITECTURE_MOTION.staggerMs).toBe(200);
    expect(ARCHITECTURE_MOTION.startScale).toBeLessThan(0.2);
    expect(easeInOutCubic(0.25)).toBeLessThan(0.25);
    expect(easeInOutCubic(0.75)).toBeGreaterThan(0.75);
    expect(easeLinear(0.37)).toBe(0.37);
  });

  it('expands planes first, then racks, then labels, then inter-plane tubes', () => {
    expect(architecturePlaneDelayMs(0)).toBe(0);
    expect(architecturePlaneDelayMs(1)).toBe(ARCHITECTURE_MOTION.staggerMs);
    expect(architecturePlanesDoneMs()).toBe(
      ARCHITECTURE_MOTION.staggerMs + ARCHITECTURE_MOTION.planeMs,
    );
    expect(architectureNodeDelayMs(0, 4)).toBe(architecturePlanesDoneMs());
    expect(architectureNodeDelayMs(1, 4)).toBe(architecturePlanesDoneMs());
    expect(architectureLabelDelayMs(0, 4)).toBe(
      architecturePlanesDoneMs() + ARCHITECTURE_MOTION.expandMs,
    );
    expect(architectureTubeDelayMs()).toBe(
      architectureLabelDelayMs() + ARCHITECTURE_MOTION.labelMs,
    );
    expect(architectureTubeDelayMs()).toBeGreaterThan(architectureLabelDelayMs());
    expect(architectureLabelDelayMs()).toBeGreaterThan(architectureNodeDelayMs());
    expect(architectureNodeDelayMs()).toBeGreaterThan(architecturePlaneDelayMs(1));
  });
});

/**
 * First-open Application Wall entrance and filter substitute motion.
 * Kept out of the legacy visual palette file so motion can change without
 * rewriting copied neon/particle constants.
 */

export const WALL_ENTRANCE = {
  sceneFadeMs: 180,
  cardStartMs: 100,
  cardDurationMs: 440,
  staggerMs: 40,
  maxStaggerMs: 340,
  reducedMotionMs: 150,
  /** World units: slightly below home. */
  offsetY: -0.28,
  /** World units: slightly farther from the camera (camera looks from +Z). */
  offsetZ: -1.4,
  startScale: 0.96,
  rotateXDeg: 2,
} as const;

export const WALL_FILTER_MOTION = {
  durationMs: 180,
  startScale: 0.98,
} as const;

export const cardStaggerDelayMs = (
  index: number,
  count: number,
  staggerMs = WALL_ENTRANCE.staggerMs,
  maxMs = WALL_ENTRANCE.maxStaggerMs,
) => {
  if (count <= 1 || index <= 0) return 0;
  const interval = Math.min(staggerMs, maxMs / Math.max(count - 1, 1));
  return Math.min(index * interval, maxMs);
};

export const wallEntranceSpanMs = (count: number) =>
  WALL_ENTRANCE.cardStartMs +
  cardStaggerDelayMs(Math.max(count - 1, 0), count) +
  WALL_ENTRANCE.cardDurationMs;

/** CSS cubic-bezier(x1, y1, x2, y2) sampled on the unit interval. */
const cubicBezier = (x1: number, y1: number, x2: number, y2: number) => {
  const sampleX = (t: number) =>
    3 * (1 - t) * (1 - t) * t * x1 + 3 * (1 - t) * t * t * x2 + t * t * t;
  const sampleY = (t: number) =>
    3 * (1 - t) * (1 - t) * t * y1 + 3 * (1 - t) * t * t * y2 + t * t * t;
  const sampleXd = (t: number) =>
    3 * (1 - t) * (1 - t) * x1 + 6 * (1 - t) * t * (x2 - x1) + 3 * t * t * (1 - x2);
  return (x: number) => {
    if (x <= 0) return 0;
    if (x >= 1) return 1;
    let t = x;
    for (let i = 0; i < 8; i += 1) {
      const xErr = sampleX(t) - x;
      const d = sampleXd(t);
      if (Math.abs(xErr) < 1e-6 || Math.abs(d) < 1e-6) break;
      t = Math.min(1, Math.max(0, t - xErr / d));
    }
    return sampleY(t);
  };
};

/** CSS cubic-bezier(0.22, 1, 0.36, 1) */
export const easeOutEntrance = cubicBezier(0.22, 1, 0.36, 1);

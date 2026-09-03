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

export const FOCUS_MOTION = {
  durationMs: 380,
  liftZ: 0.42,
  scale: 1.05,
  dimOpacity: 0.22,
  dimBright: 0.55,
} as const;

export const ARCHITECTURE_MOTION = {
  /** CubicEase-in-out camera fly; wait for this to finish before expand. */
  cameraMs: 3000,
  cameraRadiusScale: 1,
  /**
   * Extra world-Y on the landed look target (0 = plane midpoint).
   * A slight drop keeps the lampshade foot in frame at the flatter phi.
   */
  cameraTargetLift: -0.55,
  /** Extra world-Z on the landed look target (into the stack is negative). */
  cameraTargetForward: 0,
  planeMs: 420,
  expandMs: 420,
  labelMs: 280,
  tubeMs: 360,
  staggerMs: 200,
  maxStaggerMs: 2000,
  startScale: 0.08,
  /** Spawn the platforms in front of the landed camera, then ease them to rest. */
  planeStartDistance: 12,
  /** Wall cards shrink + fade out, then stay gone for the landed frame. */
  wallHideMs: 500,
  wallHideScale: 0.35,
} as const;

/** Architecture shows exactly two horizontal XZ platforms: 应用 then 主机. */
export const ARCHITECTURE_PLANE_COUNT = 2;

export const easeLinear = (t: number) => {
  if (t <= 0) return 0;
  if (t >= 1) return 1;
  return t;
};

/** Planes ease in first, staggered ~200ms (应用 → 主机). */
export const architecturePlaneDelayMs = (
  index: number,
  count = ARCHITECTURE_PLANE_COUNT,
) =>
  cardStaggerDelayMs(
    index,
    count,
    ARCHITECTURE_MOTION.staggerMs,
    ARCHITECTURE_MOTION.maxStaggerMs,
  );

export const architecturePlanesDoneMs = (count = ARCHITECTURE_PLANE_COUNT) =>
  architecturePlaneDelayMs(Math.max(count - 1, 0), count) + ARCHITECTURE_MOTION.planeMs;

/** Racks scale after every plane has finished. */
export const architectureNodeDelayMs = (_index = 0, _count = 1) => architecturePlanesDoneMs();

/** Labels appear after racks reach rest scale. */
export const architectureLabelDelayMs = (_index = 0, _count = 1) =>
  architectureNodeDelayMs() + ARCHITECTURE_MOTION.expandMs;

/** Inter-plane tubes appear after labels. */
export const architectureTubeDelayMs = () =>
  architectureLabelDelayMs() + ARCHITECTURE_MOTION.labelMs;

export const cardStaggerDelayMs = (
  index: number,
  count: number,
  staggerMs: number = WALL_ENTRANCE.staggerMs,
  maxMs: number = WALL_ENTRANCE.maxStaggerMs,
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

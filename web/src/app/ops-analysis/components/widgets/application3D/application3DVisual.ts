/**
 * Copied from app-wall-screen SystemPlane / initScene / setting.json.
 * Do not "improve" — match legacy numbers and colors.
 */

export const APPLICATION3D_ASSETS = {
  flare: '/ops-analysis/application3d/flare.png',
} as const;

export const CARD_WORLD_WIDTH = 4.6;
export const CARD_WORLD_HEIGHT = 1.92;
export const CARD_ASPECT = CARD_WORLD_WIDTH / CARD_WORLD_HEIGHT;
export const CARD_GAP = 0.38;
export const CARD_TEXTURE_WIDTH = 768;
export const CARD_TEXTURE_HEIGHT = 320;

export type Application3DNeonLevel = 'normal' | 'fatal' | 'error' | 'warning' | 'info' | 'remain';

export const NEON_PANEL: Record<
  Application3DNeonLevel,
  { gradient: string; border: string; shadow: string }
> = {
  normal: {
    gradient: 'var(--color-application3d-panel-normal-gradient)',
    border: '2px solid var(--color-application3d-panel-normal-border)',
    shadow: 'var(--color-application3d-panel-normal-shadow)',
  },
  fatal: {
    gradient: 'var(--color-application3d-panel-fatal-gradient)',
    border: '2px solid var(--color-application3d-panel-fatal-border)',
    shadow: 'var(--color-application3d-panel-fatal-shadow)',
  },
  error: {
    gradient: 'var(--color-application3d-panel-error-gradient)',
    border: '2px solid var(--color-application3d-panel-error-border)',
    shadow: 'var(--color-application3d-panel-error-shadow)',
  },
  warning: {
    gradient: 'var(--color-application3d-panel-warning-gradient)',
    border: '2px solid var(--color-application3d-panel-warning-border)',
    shadow: 'var(--color-application3d-panel-warning-shadow)',
  },
  info: {
    gradient: 'var(--color-application3d-panel-info-gradient)',
    border: '2px solid var(--color-application3d-panel-info-border)',
    shadow: 'var(--color-application3d-panel-info-shadow)',
  },
  remain: {
    gradient: 'var(--color-application3d-panel-remain-gradient)',
    border: '2px solid var(--color-application3d-panel-remain-border)',
    shadow: 'var(--color-application3d-panel-remain-shadow)',
  },
};

/** Legacy ParticleSystem (initScene.js) */
export const LEGACY_PARTICLE = {
  /** Scaled down for widget GPU; faint starfield, not a glowing volume. */
  capacity: 420,
  color1: { r: 0.55, g: 0.65, b: 0.82, a: 0.7 },
  color2: { r: 0.18, g: 0.32, b: 0.55, a: 0.45 },
  colorDead: { r: 0, g: 0, b: 0.2, a: 0 },
  minSize: 0.1,
  maxSize: 0.5,
  minLifeTime: 0.3,
  maxLifeTime: 1.5,
  /** Babylon default emit direction is +Y with emitPower ~1. */
  minEmitPower: 0.6,
  maxEmitPower: 1.4,
  emitBox: 28,
} as const;

/** Babylon: 0→100 @ 60fps / speedRatio */
export const durationFromSpeed = (speed: number) => 100 / 60 / Math.max(speed, 0.01);

export const easeInOutCubic = (t: number) =>
  t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;

export const resolveNeonLevel = (item: {
  health: {
    state: string;
    reason: string;
    highestSeverity: { id: string; color: string } | null;
  };
}): Application3DNeonLevel => {
  if (item.health.state === 'normal') return 'normal';
  if (item.health.state === 'unknown') return 'remain';
  const color = item.health.highestSeverity?.color || item.health.highestSeverity?.id || '';
  if (color === 'critical' || color === 'fail') return 'fatal';
  if (color === 'error' || color === 'danger') return 'error';
  if (color === 'warning') return 'warning';
  if (color === 'info') return 'info';
  // alarming but highestSeverity missing (non-empty unmapped level): warning, never fatal.
  // Empty MonitorAlert.level is already normalized to warning on the backend.
  if (item.health.state === 'alarming') return 'warning';
  return 'remain';
};

export const prefersReducedMotion = () =>
  typeof window !== 'undefined' &&
  Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);

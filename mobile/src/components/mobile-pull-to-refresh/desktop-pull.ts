export const DESKTOP_PULL_THRESHOLD = 72;

const DIRECTION_LOCK_DISTANCE = 8;
const MAX_HEAD_OFFSET = 64;

export type DesktopPullIntent = 'pending' | 'cancelled' | 'pulling';

export function getDesktopPullIntent(deltaX: number, deltaY: number): DesktopPullIntent {
  if (Math.abs(deltaX) < DIRECTION_LOCK_DISTANCE && Math.abs(deltaY) < DIRECTION_LOCK_DISTANCE) {
    return 'pending';
  }
  if (deltaY <= 0 || Math.abs(deltaX) > Math.abs(deltaY)) return 'cancelled';
  return 'pulling';
}

export function getDesktopPullProgress(deltaY: number) {
  const distance = Math.max(0, deltaY);
  const easedDistance = distance <= DESKTOP_PULL_THRESHOLD
    ? distance * 0.65
    : DESKTOP_PULL_THRESHOLD * 0.65 + (distance - DESKTOP_PULL_THRESHOLD) * 0.18;

  return {
    canRelease: distance >= DESKTOP_PULL_THRESHOLD,
    headOffset: Math.min(MAX_HEAD_OFFSET, Math.round(easedDistance)),
  };
}

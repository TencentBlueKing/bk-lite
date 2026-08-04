export type CleanupTimeoutUnit = 'minute' | 'hour' | 'day';

interface CleanupTimeoutSource {
  cleanup_timeout_value?: number;
  cleanup_timeout_unit?: CleanupTimeoutUnit;
  cleanup_timeout_days?: number;
}

const CLEANUP_TIMEOUT_MAX_BY_UNIT: Record<CleanupTimeoutUnit, number> = {
  minute: 1440,
  hour: 720,
  day: 365
};

export const getCleanupTimeoutMax = (unit: CleanupTimeoutUnit): number =>
  CLEANUP_TIMEOUT_MAX_BY_UNIT[unit];

export const normalizeCleanupTimeout = (
  source: CleanupTimeoutSource
): { value: number; unit: CleanupTimeoutUnit } => ({
  value: source.cleanup_timeout_value ?? source.cleanup_timeout_days ?? 1,
  unit: source.cleanup_timeout_unit ?? 'day'
});

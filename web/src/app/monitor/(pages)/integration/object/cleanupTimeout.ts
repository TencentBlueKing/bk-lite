export type CleanupTimeoutUnit = 'day' | 'minute';

interface CleanupTimeoutSource {
  cleanup_timeout_value?: number;
  cleanup_timeout_unit?: CleanupTimeoutUnit;
  cleanup_timeout_days?: number;
}

export const getCleanupTimeoutMax = (unit: CleanupTimeoutUnit): number =>
  unit === 'minute' ? 1440 : 365;

export const normalizeCleanupTimeout = (
  source: CleanupTimeoutSource
): { value: number; unit: CleanupTimeoutUnit } => ({
  value: source.cleanup_timeout_value ?? source.cleanup_timeout_days ?? 1,
  unit: source.cleanup_timeout_unit ?? 'day'
});

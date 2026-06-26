export const TARGET_QUERY_POINTS = 100;

const normalizeMinStepSeconds = (value: unknown): number => {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue) || numericValue <= 0) {
    return 0;
  }
  return Math.ceil(numericValue);
};

export const calculateQueryStep = (
  startMs: number,
  endMs: number,
  minStepSeconds?: unknown
): number => {
  const durationSeconds = Math.max((endMs - startMs) / 1000, 0);
  const targetStepSeconds = Math.ceil(durationSeconds / TARGET_QUERY_POINTS);
  return Math.max(targetStepSeconds, normalizeMinStepSeconds(minStepSeconds), 1);
};

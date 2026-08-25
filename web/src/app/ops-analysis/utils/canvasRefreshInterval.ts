export const CANVAS_REFRESH_INTERVAL_MS = [0, 60_000, 300_000, 600_000] as const;

export type CanvasRefreshIntervalMs = (typeof CANVAS_REFRESH_INTERVAL_MS)[number];

export const DEFAULT_CANVAS_REFRESH_INTERVAL_MS = 0;

export const isCanvasRefreshIntervalMs = (
  value: unknown,
): value is CanvasRefreshIntervalMs =>
  typeof value === 'number' &&
  (CANVAS_REFRESH_INTERVAL_MS as readonly number[]).includes(value);

export const normalizeCanvasRefreshInterval = (
  value: unknown,
): CanvasRefreshIntervalMs => {
  const parsed =
    typeof value === 'number'
      ? value
      : typeof value === 'string' && value.trim() !== ''
        ? Number(value)
        : NaN;
  if (isCanvasRefreshIntervalMs(parsed)) {
    return parsed;
  }
  return DEFAULT_CANVAS_REFRESH_INTERVAL_MS;
};

export const canPersistCanvasRefreshInterval = ({
  shareMode,
  isBuiltIn,
  hasEditPermission,
}: {
  shareMode: boolean;
  isBuiltIn: boolean;
  hasEditPermission: boolean;
}): boolean => !shareMode && !isBuiltIn && hasEditPermission;

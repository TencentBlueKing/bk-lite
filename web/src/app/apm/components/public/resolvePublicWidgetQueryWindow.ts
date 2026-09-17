const ONE_HOUR_MS = 60 * 60 * 1000;

export function recentPublicWidgetWindow(
  now: Date = new Date(),
): { startedAt: string; endedAt: string } {
  return {
    startedAt: new Date(now.getTime() - ONE_HOUR_MS).toISOString(),
    endedAt: now.toISOString(),
  };
}

/** 宿主传入的 ISO 窗优先；缺一、无效或顺序颠倒则回落 now−1h。 */
export function resolvePublicWidgetQueryWindow(
  startedAt?: string,
  endedAt?: string,
  now: Date = new Date(),
): { startedAt: string; endedAt: string } {
  const start = String(startedAt || '').trim();
  const end = String(endedAt || '').trim();
  if (start && end) {
    const startMs = Date.parse(start);
    const endMs = Date.parse(end);
    if (
      Number.isFinite(startMs) &&
      Number.isFinite(endMs) &&
      startMs < endMs
    ) {
      return {
        startedAt: new Date(startMs).toISOString(),
        endedAt: new Date(endMs).toISOString(),
      };
    }
  }
  return recentPublicWidgetWindow(now);
}

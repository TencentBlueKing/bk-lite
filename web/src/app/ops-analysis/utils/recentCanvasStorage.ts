import { isCanvasType, type CanvasType } from '@/app/ops-analysis/constants/canvasTypes';

export const RECENT_CANVAS_STORAGE_KEY = 'bk-lite:ops-analysis:recent-canvases';
export const MAX_RECENT_CANVASES = 10;
export const RECENT_CANVAS_DISPLAY_COUNT = 3;

export interface RecentCanvasRecord {
  id: string;
  dataId: string;
  type: CanvasType;
  name: string;
  viewedAt: number;
}

interface StorageLike {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
}

export type RecentViewedLabel =
  | { key: 'opsAnalysisSidebar.recentJustNow' }
  | { key: 'opsAnalysisSidebar.recentMinutesAgo'; count: number }
  | { key: 'opsAnalysisSidebar.recentHoursAgo'; count: number }
  | { key: 'opsAnalysisSidebar.recentYesterday' }
  | { key: 'opsAnalysisSidebar.recentDaysAgo'; count: number };

const MINUTE = 60 * 1000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

const isRecentCanvasRecord = (value: unknown): value is RecentCanvasRecord => {
  if (!value || typeof value !== 'object') return false;
  const record = value as RecentCanvasRecord;
  return (
    typeof record.id === 'string' &&
    record.id.length > 0 &&
    typeof record.dataId === 'string' &&
    record.dataId.length > 0 &&
    isCanvasType(record.type) &&
    typeof record.name === 'string' &&
    record.name.length > 0 &&
    typeof record.viewedAt === 'number' &&
    Number.isFinite(record.viewedAt)
  );
};

export const normalizeRecentCanvasRecords = (value: unknown): RecentCanvasRecord[] => {
  if (!Array.isArray(value)) return [];

  const seen = new Set<string>();
  const records: RecentCanvasRecord[] = [];

  for (const item of value) {
    if (!isRecentCanvasRecord(item)) continue;
    if (seen.has(item.id)) continue;
    seen.add(item.id);
    records.push(item);
  }

  return records.slice(0, MAX_RECENT_CANVASES);
};

export const readRecentCanvases = (
  storage: Pick<StorageLike, 'getItem'> | null,
): RecentCanvasRecord[] => {
  if (!storage) return [];
  try {
    const rawValue = storage.getItem(RECENT_CANVAS_STORAGE_KEY);
    return rawValue ? normalizeRecentCanvasRecords(JSON.parse(rawValue)) : [];
  } catch {
    return [];
  }
};

export const recordRecentCanvas = (
  storage: Pick<StorageLike, 'getItem' | 'setItem'> | null,
  canvas: Omit<RecentCanvasRecord, 'viewedAt'>,
): RecentCanvasRecord[] => {
  const normalizedCanvas = {
    id: String(canvas.id ?? ''),
    dataId: String(canvas.dataId ?? ''),
    type: canvas.type,
    name: String(canvas.name ?? ''),
  };

  if (
    !storage ||
    !normalizedCanvas.id ||
    !normalizedCanvas.dataId ||
    !normalizedCanvas.name ||
    !isCanvasType(normalizedCanvas.type)
  ) {
    return storage ? readRecentCanvases(storage) : [];
  }

  const next = normalizeRecentCanvasRecords([
    { ...normalizedCanvas, viewedAt: Date.now() },
    ...readRecentCanvases(storage),
  ]);

  try {
    storage.setItem(RECENT_CANVAS_STORAGE_KEY, JSON.stringify(next));
  } catch {
    // Quota/private mode should not block normal navigation.
  }

  return next;
};

export const getDisplayRecentCanvases = (
  records: RecentCanvasRecord[],
): RecentCanvasRecord[] => records.slice(0, RECENT_CANVAS_DISPLAY_COUNT);

export const getRecentViewedLabel = (
  viewedAt: number,
  now = Date.now(),
): RecentViewedLabel => {
  const delta = Math.max(0, now - viewedAt);
  if (delta < MINUTE) return { key: 'opsAnalysisSidebar.recentJustNow' };
  if (delta < HOUR) {
    return {
      key: 'opsAnalysisSidebar.recentMinutesAgo',
      count: Math.max(1, Math.floor(delta / MINUTE)),
    };
  }
  if (delta < DAY) {
    return {
      key: 'opsAnalysisSidebar.recentHoursAgo',
      count: Math.max(1, Math.floor(delta / HOUR)),
    };
  }
  if (delta < 2 * DAY) return { key: 'opsAnalysisSidebar.recentYesterday' };
  return {
    key: 'opsAnalysisSidebar.recentDaysAgo',
    count: Math.max(2, Math.floor(delta / DAY)),
  };
};

export type EventTimelineStatus =
  | 'info'
  | 'warning'
  | 'error'
  | 'success'
  | 'unknown'
  | 'neutral';

export interface EventTimelineItem {
  time: string;
  title: string;
  description?: string;
  category?: string;
  status?: EventTimelineStatus;
  link?: string;
}

export interface EventTimelineParseResult {
  items: EventTimelineItem[];
  total: number;
  truncated: boolean;
}

export const DEFAULT_EVENT_TIMELINE_MAX_ITEMS = 100;

const toStatus = (value: unknown): EventTimelineStatus | undefined => {
  if (value === undefined || value === null) return undefined;
  if (typeof value !== 'string') return 'unknown';
  const normalized = value.trim().toLowerCase();
  if (!normalized) return undefined;
  if (
    normalized === 'info' ||
    normalized === 'warning' ||
    normalized === 'error' ||
    normalized === 'success'
  ) {
    return normalized;
  }
  if (normalized === 'neutral') {
    return 'neutral';
  }
  return 'unknown';
};

const toNonEmptyText = (value: unknown): string | undefined => {
  if (value === undefined || value === null) return undefined;
  const text = String(value).trim();
  return text ? text : undefined;
};

const extractEventRows = (rawData: unknown): Record<string, unknown>[] => {
  if (Array.isArray(rawData)) {
    return rawData.filter(
      (item): item is Record<string, unknown> =>
        Boolean(item) && typeof item === 'object' && !Array.isArray(item),
    );
  }

  if (!rawData || typeof rawData !== 'object') {
    return [];
  }

  const objectData = rawData as Record<string, unknown>;
  if (Array.isArray(objectData.items)) {
    return objectData.items.filter(
      (item): item is Record<string, unknown> =>
        Boolean(item) && typeof item === 'object' && !Array.isArray(item),
    );
  }

  return [];
};

const toEventItem = (row: Record<string, unknown>): EventTimelineItem | null => {
  const time = toNonEmptyText(row.time);
  const title = toNonEmptyText(row.title);

  if (!time || !title) {
    return null;
  }

  const description = toNonEmptyText(row.description);
  const category = toNonEmptyText(row.category);
  const status = toStatus(row.status);
  const link = toNonEmptyText(row.link);

  return {
    time,
    title,
    ...(description ? { description } : {}),
    ...(category ? { category } : {}),
    ...(status ? { status } : {}),
    ...(link ? { link } : {}),
  };
};

const compareByTimeAsc = (left: EventTimelineItem, right: EventTimelineItem) => {
  const leftTs = Date.parse(left.time);
  const rightTs = Date.parse(right.time);

  if (Number.isFinite(leftTs) && Number.isFinite(rightTs)) {
    return leftTs - rightTs;
  }

  return left.time.localeCompare(right.time);
};

export const isEmptyEventTimelinePayload = (rawData: unknown): boolean => {
  if (rawData === null || rawData === undefined) {
    return true;
  }
  if (Array.isArray(rawData)) {
    return rawData.length === 0;
  }
  if (typeof rawData === 'object') {
    const items = (rawData as Record<string, unknown>).items;
    if (Array.isArray(items)) {
      return items.length === 0;
    }
  }
  return false;
};

export const parseEventTimelineItems = (
  rawData: unknown,
  options?: {
    sortOrder?: 'asc' | 'desc';
    maxItems?: number;
  },
): EventTimelineParseResult => {
  const rows = extractEventRows(rawData);
  const mapped = rows
    .map((row) => toEventItem(row))
    .filter((item): item is EventTimelineItem => item !== null);
  const sorted = mapped.sort(compareByTimeAsc);
  const descending = options?.sortOrder !== 'asc';
  const maxItems = Number.isFinite(options?.maxItems)
    ? Math.max(1, Number(options?.maxItems))
    : DEFAULT_EVENT_TIMELINE_MAX_ITEMS;
  const latestWindow =
    sorted.length > maxItems ? sorted.slice(sorted.length - maxItems) : sorted;
  const sliced = descending ? [...latestWindow].reverse() : latestWindow;

  return {
    items: sliced,
    total: sorted.length,
    truncated: sorted.length > sliced.length,
  };
};

export const validateEventTimelinePayload = (
  rawData: unknown,
): { isValid: boolean; message?: string } => {
  if (isEmptyEventTimelinePayload(rawData)) {
    return { isValid: true };
  }

  const parsed = parseEventTimelineItems(rawData);
  if (parsed.total === 0) {
    return {
      isValid: false,
      message:
        '数据结构不符：事件时间线期望包含 time 与 title 字段的事件列表',
    };
  }

  return { isValid: true };
};

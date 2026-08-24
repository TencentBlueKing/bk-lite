import type { TimeValuesProps } from '@/app/monitor/types';

const parseEpochMs = (raw: string | null): number | null => {
  if (!raw) return null;
  const value = Number(raw);
  if (!Number.isFinite(value) || value <= 0) return null;
  return value;
};

const parsePositiveMinutes = (raw: string | null): number | null => {
  if (!raw) return null;
  const value = Number(raw);
  if (!Number.isInteger(value) || value <= 0) return null;
  return value;
};

export interface ParsedSearchTimeQuery {
  timeValues: TimeValuesProps;
  selectValue: number;
  rangeStart: number | null;
  rangeEnd: number | null;
}

const DEFAULT_SEARCH_TIME: ParsedSearchTimeQuery = {
  timeValues: { timeRange: [], originValue: 15 },
  selectValue: 15,
  rangeStart: null,
  rangeEnd: null
};

/** 详情放大镜跳转 Search 时携带时间：相对用 origin，自定义区间用 start/end。 */
export const buildSearchTimeQueryParams = (
  timeValues: TimeValuesProps
): Record<string, string> => {
  const origin = timeValues.originValue;
  if (typeof origin === 'number' && origin > 0) {
    return { origin: String(origin) };
  }
  const start = timeValues.timeRange?.[0];
  const end = timeValues.timeRange?.[1];
  if (
    Number.isFinite(start) &&
    Number.isFinite(end) &&
    Number(start) < Number(end)
  ) {
    return { start: String(start), end: String(end) };
  }
  return {};
};

export const parseSearchTimeQueryParams = (params: {
  get: (name: string) => string | null;
}): ParsedSearchTimeQuery => {
  const origin = parsePositiveMinutes(params.get('origin'));
  if (origin) {
    return {
      timeValues: { timeRange: [], originValue: origin },
      selectValue: origin,
      rangeStart: null,
      rangeEnd: null
    };
  }
  const start = parseEpochMs(params.get('start'));
  const end = parseEpochMs(params.get('end'));
  if (start != null && end != null && start < end) {
    return {
      timeValues: { timeRange: [start, end], originValue: 0 },
      selectValue: 0,
      rangeStart: start,
      rangeEnd: end
    };
  }
  return DEFAULT_SEARCH_TIME;
};

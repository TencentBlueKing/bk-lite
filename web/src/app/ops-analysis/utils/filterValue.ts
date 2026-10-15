import dayjs, { type Dayjs } from 'dayjs';

import type { TimeRangeValue } from '@/app/ops-analysis/types/dashBoard';

const toReferenceTime = (referenceTime?: string | Date | number) => {
  const parsed = referenceTime ? dayjs(referenceTime) : dayjs();
  return parsed.isValid() ? parsed : dayjs();
};

export const buildRelativeTimeRangeFilterValue = (
  minutes: number,
  referenceTime?: string | Date | number,
): TimeRangeValue => {
  const end = toReferenceTime(referenceTime);
  const start = end.subtract(minutes, 'minute');

  return {
    start: start.toISOString(),
    end: end.toISOString(),
    selectValue: minutes,
  };
};

export const normalizeTimeRangeFilterValue = (
  value: unknown,
  referenceTime?: string | Date | number,
): TimeRangeValue | null => {
  if (typeof value === 'number' && Number.isFinite(value) && value > 0) {
    return buildRelativeTimeRangeFilterValue(value, referenceTime);
  }

  if (!value || typeof value !== 'object') {
    return null;
  }

  const candidate = value as Partial<TimeRangeValue>;
  if (
    typeof candidate.selectValue === 'number' &&
    Number.isFinite(candidate.selectValue) &&
    candidate.selectValue > 0
  ) {
    return buildRelativeTimeRangeFilterValue(
      candidate.selectValue,
      referenceTime,
    );
  }

  if (!candidate.start || !candidate.end) {
    return null;
  }

  return {
    start: String(candidate.start),
    end: String(candidate.end),
    ...(typeof candidate.selectValue === 'number'
      ? { selectValue: candidate.selectValue }
      : {}),
  };
};

export interface UnifiedFilterTimeSelectorDefault {
  selectValue: number;
  rangePickerVaule: [Dayjs, Dayjs] | null;
}

/** 配置弹窗与筛选栏共用：先归一化，selectValue>0 即相对时间，不要求已有 start/end。 */
export const getUnifiedFilterTimeSelectorDefaultValue = (
  value: unknown,
  referenceTime?: string | Date | number,
): UnifiedFilterTimeSelectorDefault => {
  const normalized = normalizeTimeRangeFilterValue(value, referenceTime);
  if (!normalized?.start || !normalized?.end) {
    return { selectValue: 15, rangePickerVaule: null };
  }

  const selectValue = normalized.selectValue ?? 0;
  if (selectValue > 0) {
    return { selectValue, rangePickerVaule: null };
  }

  return {
    selectValue: 0,
    rangePickerVaule: [dayjs(normalized.start), dayjs(normalized.end)],
  };
};
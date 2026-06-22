import dayjs from 'dayjs';

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
  if (!candidate.start || !candidate.end) {
    return null;
  }

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

  return {
    start: String(candidate.start),
    end: String(candidate.end),
    ...(typeof candidate.selectValue === 'number'
      ? { selectValue: candidate.selectValue }
      : {}),
  };
};
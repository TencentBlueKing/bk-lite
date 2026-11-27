import dayjs, { type Dayjs } from 'dayjs';

import type { TimeRangeValue } from '@/app/ops-analysis/types/dashBoard';

const toReferenceTime = (referenceTime?: string | Date | number) => {
  const parsed = referenceTime ? dayjs(referenceTime) : dayjs();
  return parsed.isValid() ? parsed : dayjs();
};

/** 时间控件回调里的快捷项只留分钟数；自定义区间才写下起止。 */
export const timeRangeValueFromSelector = (
  range: number[],
  originValue: number | null,
): TimeRangeValue | null => {
  if (range.length !== 2) {
    return null;
  }
  if (typeof originValue === 'number' && Number.isFinite(originValue) && originValue > 0) {
    return { selectValue: originValue };
  }
  return {
    start: dayjs(range[0]).toISOString(),
    end: dayjs(range[1]).toISOString(),
    selectValue: originValue ?? 0,
  };
};

/** 快捷项落盘时丢掉起止，只留分钟数。 */
export const persistedTimeRangeFilterValue = (
  value: TimeRangeValue | null,
): TimeRangeValue | null => {
  if (!value) {
    return null;
  }
  if (
    typeof value.selectValue === 'number'
    && Number.isFinite(value.selectValue)
    && value.selectValue > 0
  ) {
    return { selectValue: value.selectValue };
  }
  return value;
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
  selectValue: number | null;
  rangePickerVaule: [Dayjs, Dayjs] | null;
}

/** 配置弹窗与筛选栏共用：先归一化，selectValue>0 即相对时间，不要求已有 start/end。空值保持空，不发明造的 15 分钟。 */
export const getUnifiedFilterTimeSelectorDefaultValue = (
  value: unknown,
  referenceTime?: string | Date | number,
): UnifiedFilterTimeSelectorDefault => {
  const normalized = normalizeTimeRangeFilterValue(value, referenceTime);
  if (!normalized?.start || !normalized?.end) {
    return { selectValue: null, rangePickerVaule: null };
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
import dayjs, { Dayjs } from 'dayjs';
import customParseFormat from 'dayjs/plugin/customParseFormat';

import {
  DateRangeValue,
} from '@/app/ops-analysis/types/dateRange';

dayjs.extend(customParseFormat);

export type DateRangePickerValue = [Dayjs | null, Dayjs | null] | null;

/** 只展示已写入的值；未设置时保持空，避免把「最近 7 天」当成已生效条件。 */
export const getDateRangeSelectorValue = (
  value: DateRangeValue | null | undefined,
): DateRangeValue | null => value ?? null;

export const toDateRangePickerValue = (
  value: DateRangeValue | null | undefined,
): [Dayjs, Dayjs] | null => {
  if (value?.rangeType !== 'custom') return null;

  const start = dayjs(value.startDate, 'YYYY-MM-DD', true);
  const end = dayjs(value.endDate, 'YYYY-MM-DD', true);
  return start.isValid() && end.isValid() ? [start, end] : null;
};

export const completeCustomDateRange = (
  dates: DateRangePickerValue,
): DateRangeValue | null => {
  const [start, end] = dates ?? [];
  if (!start || !end) return null;

  return {
    rangeType: 'custom',
    startDate: start.format('YYYY-MM-DD'),
    endDate: end.format('YYYY-MM-DD'),
  };
};

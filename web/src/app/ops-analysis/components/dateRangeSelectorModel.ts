import dayjs, { Dayjs } from 'dayjs';
import customParseFormat from 'dayjs/plugin/customParseFormat';

import {
  DEFAULT_DATE_RANGE_VALUE,
  DateRangeValue,
} from '@/app/ops-analysis/types/dateRange';

dayjs.extend(customParseFormat);

export type DateRangePickerValue = [Dayjs | null, Dayjs | null] | null;

export const getDateRangeSelectorValue = (
  value: DateRangeValue | null | undefined,
): DateRangeValue | null => value === undefined
  ? { ...DEFAULT_DATE_RANGE_VALUE }
  : value;

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

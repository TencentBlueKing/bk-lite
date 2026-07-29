import dayjs, { Dayjs } from 'dayjs';
import customParseFormat from 'dayjs/plugin/customParseFormat';
import timezone from 'dayjs/plugin/timezone';
import utc from 'dayjs/plugin/utc';

import {
  DATE_RANGE_TYPES,
  DateRangeType,
  DateRangeValue,
  ResolvedDateRange,
} from '../types/dateRange';

dayjs.extend(customParseFormat);
dayjs.extend(utc);
dayjs.extend(timezone);

export interface DateRangeValidationResult {
  valid: boolean;
  error?: string;
}

export interface DateRangeResolutionContext {
  referenceNow: string | number | Date;
  timezone: string;
}

const QUICK_RANGE_TYPES = new Set<DateRangeType>(
  DATE_RANGE_TYPES.filter((rangeType) => rangeType !== 'custom'),
);
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

const invalid = (error: string): DateRangeValidationResult => ({
  valid: false,
  error,
});

const isStrictDate = (value: unknown): value is string =>
  typeof value === 'string'
  && DATE_PATTERN.test(value)
  && dayjs(value, 'YYYY-MM-DD', true).isValid();

export const validateDateRangeValue = (
  value: unknown,
): DateRangeValidationResult => {
  if (value === null) return { valid: true };
  if (typeof value !== 'object' || Array.isArray(value)) {
    return invalid('dateRange must be an object or null');
  }

  const candidate = value as Record<string, unknown>;
  if (typeof candidate.rangeType !== 'string'
    || !DATE_RANGE_TYPES.includes(candidate.rangeType as DateRangeType)) {
    return invalid('dateRange has an unknown rangeType');
  }

  if (candidate.rangeType === 'custom') {
    if (Object.keys(candidate).some(
      (key) => !['rangeType', 'startDate', 'endDate'].includes(key),
    )) {
      return invalid('custom dateRange has conflicting fields');
    }
    if (!isStrictDate(candidate.startDate) || !isStrictDate(candidate.endDate)) {
      return invalid('custom dateRange requires strict YYYY-MM-DD dates');
    }
    if (candidate.startDate > candidate.endDate) {
      return invalid('custom dateRange startDate must not exceed endDate');
    }
    return { valid: true };
  }

  if (!QUICK_RANGE_TYPES.has(candidate.rangeType as DateRangeType)) {
    return invalid('dateRange has an unknown rangeType');
  }
  if (Object.keys(candidate).some((key) => key !== 'rangeType')) {
    return invalid('quick dateRange must not contain custom fields');
  }
  return { valid: true };
};

const isValidTimezone = (timezoneName: string): boolean => {
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: timezoneName }).format();
    return true;
  } catch {
    return false;
  }
};

export const getDateRangeTimezone = (configuredTimezone?: string): string => {
  const configured = configuredTimezone?.trim();
  if (configured && isValidTimezone(configured)) return configured;
  if (typeof Intl !== 'undefined') {
    const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (browserTimezone && isValidTimezone(browserTimezone)) return browserTimezone;
  }
  return 'UTC';
};

export const resolveDateRange = (
  value: unknown,
  context: DateRangeResolutionContext,
): ResolvedDateRange | null => {
  const validation = validateDateRangeValue(value);
  if (!validation.valid || value === null) return null;

  const dateRange = value as DateRangeValue;
  if (dateRange.rangeType === 'custom') {
    return [dateRange.startDate, dateRange.endDate];
  }

  const resolvedTimezone = getDateRangeTimezone(context.timezone);
  const today = dayjs(context.referenceNow).tz(resolvedTimezone).startOf('day');
  const monday = today.subtract((today.day() + 6) % 7, 'day');
  const previousMonth = today.subtract(1, 'month');
  const ranges: Record<Exclude<DateRangeType, 'custom'>, [Dayjs, Dayjs]> = {
    today: [today, today],
    yesterday: [today.subtract(1, 'day'), today.subtract(1, 'day')],
    this_week: [monday, today],
    last_week: [monday.subtract(7, 'day'), monday.subtract(1, 'day')],
    this_month: [today.startOf('month'), today],
    last_month: [previousMonth.startOf('month'), previousMonth.endOf('month')],
    last_7_days: [today.subtract(6, 'day'), today],
    last_30_days: [today.subtract(29, 'day'), today],
    last_90_days: [today.subtract(89, 'day'), today],
  };
  const [start, end] = ranges[dateRange.rangeType];
  return [start.format('YYYY-MM-DD'), end.format('YYYY-MM-DD')];
};

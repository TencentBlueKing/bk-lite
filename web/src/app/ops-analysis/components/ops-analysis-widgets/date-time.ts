import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';
import timezone from 'dayjs/plugin/timezone';
import { getStoredTimezone, normalizeTimezone } from '@/utils/userPreferences';

dayjs.extend(utc);
dayjs.extend(timezone);

const NUMERIC_REGEXP = /^\d+(?:\.\d+)?$/;

const getCurrentTimezone = () => normalizeTimezone(getStoredTimezone());

const hasExplicitTimezone = (value: string) =>
  /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value.trim());

const toDayjs = (value: unknown) => {
  if (typeof value === 'number') {
    const timestamp = value > 9999999999 ? value : value * 1000;
    return dayjs(timestamp);
  }

  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed) {
      return null;
    }

    if (NUMERIC_REGEXP.test(trimmed)) {
      const numericValue = Number(trimmed);
      const timestamp = numericValue > 9999999999 ? numericValue : numericValue * 1000;
      return dayjs(timestamp);
    }

    if (hasExplicitTimezone(trimmed)) {
      const parsed = dayjs(trimmed);
      return parsed.isValid() ? parsed : null;
    }

    const parsed = dayjs.utc(trimmed);
    return parsed.isValid() ? parsed : null;
  }

  const parsed = dayjs(value as dayjs.ConfigType);
  return parsed.isValid() ? parsed : null;
};

export const formatOpsRequestTime = (value: unknown): string => {
  const parsed = toDayjs(value);
  if (!parsed) {
    return String(value ?? '');
  }
  return parsed.toISOString();
};

export const formatOpsDisplayTime = (
  value: unknown,
  format: string = 'YYYY-MM-DD HH:mm:ss',
): string => {
  const parsed = toDayjs(value);
  if (!parsed) {
    return String(value ?? '');
  }

  const timezoneName = getCurrentTimezone();
  try {
    return parsed.tz(timezoneName).format(format);
  } catch {
    return parsed.format(format);
  }
};

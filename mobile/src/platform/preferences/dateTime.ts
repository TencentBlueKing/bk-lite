export interface DateTimePreferences {
  locale: string;
  timezone: string;
}

const DEFAULT_LOCALE = 'en';
const DEFAULT_TIMEZONE = 'Asia/Shanghai';

export function normalizeAccountLocale(locale?: string | null): string {
  if (!locale) return DEFAULT_LOCALE;
  const normalized = locale.trim().toLowerCase();
  if (normalized.startsWith('zh')) return 'zh-Hans';
  if (normalized.startsWith('en')) return 'en';
  return DEFAULT_LOCALE;
}

export function normalizeAccountTimezone(timezone?: string | null): string {
  const candidate = timezone?.trim() || DEFAULT_TIMEZONE;
  try {
    new Intl.DateTimeFormat('en', { timeZone: candidate }).format(0);
    return candidate;
  } catch {
    return DEFAULT_TIMEZONE;
  }
}

function toDate(value: string | number | Date): Date | null {
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function dateParts(date: Date, preferences: DateTimePreferences) {
  const formatter = new Intl.DateTimeFormat('en-CA', {
    timeZone: normalizeAccountTimezone(preferences.timezone),
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });
  const parts = Object.fromEntries(
    formatter.formatToParts(date).map((part) => [part.type, part.value]),
  );
  return {
    year: Number(parts.year),
    month: Number(parts.month),
    day: Number(parts.day),
    key: `${parts.year}-${parts.month}-${parts.day}`,
  };
}

function previousDateKey(parts: { year: number; month: number; day: number }) {
  const value = new Date(Date.UTC(parts.year, parts.month - 1, parts.day - 1));
  return [
    value.getUTCFullYear(),
    String(value.getUTCMonth() + 1).padStart(2, '0'),
    String(value.getUTCDate()).padStart(2, '0'),
  ].join('-');
}

function formatter(preferences: DateTimePreferences, options: Intl.DateTimeFormatOptions) {
  return new Intl.DateTimeFormat(normalizeAccountLocale(preferences.locale), {
    ...options,
    timeZone: normalizeAccountTimezone(preferences.timezone),
  });
}

export function formatAccountDateTime(
  value: string | number | Date,
  preferences: DateTimePreferences,
  options: Intl.DateTimeFormatOptions = {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  },
): string {
  const date = toDate(value);
  if (!date) return '';
  return formatter(preferences, options).format(date);
}

export function formatAccountActivity(
  value: string | number | Date,
  preferences: DateTimePreferences,
  yesterdayLabel: string,
  nowValue: Date = new Date(),
): string {
  const date = toDate(value);
  if (!date) return '';
  const current = dateParts(nowValue, preferences);
  const target = dateParts(date, preferences);
  const time = formatter(preferences, {
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);

  if (target.key === current.key) return time;
  if (target.key === previousDateKey(current)) return `${yesterdayLabel} ${time}`;

  return formatter(preferences, {
    year: target.year === current.year ? undefined : 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(date);
}

export function formatAccountMessageTime(
  value: string | number | Date,
  preferences: DateTimePreferences,
  yesterdayLabel: string,
  nowValue: Date = new Date(),
): string {
  const date = toDate(value);
  if (!date) return '';
  const current = dateParts(nowValue, preferences);
  const target = dateParts(date, preferences);
  const time = formatter(preferences, {
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);

  if (target.key === current.key) return time;
  if (target.key === previousDateKey(current)) return `${yesterdayLabel} ${time}`;
  return formatter(preferences, {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

export function formatAccountSearchTime(
  value: string | number | Date,
  preferences: DateTimePreferences,
  yesterdayLabel: string,
  nowValue: Date = new Date(),
): string {
  const date = toDate(value);
  if (!date) return '';
  const current = dateParts(nowValue, preferences);
  const target = dateParts(date, preferences);

  if (target.key === current.key) {
    return formatter(preferences, { hour: '2-digit', minute: '2-digit' }).format(date);
  }
  if (target.key === previousDateKey(current)) return yesterdayLabel;
  if (nowValue.getTime() - date.getTime() < 7 * 24 * 60 * 60 * 1000) {
    return formatter(preferences, { weekday: 'short' }).format(date);
  }
  return formatter(preferences, {
    year: target.year === current.year ? undefined : 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(date);
}

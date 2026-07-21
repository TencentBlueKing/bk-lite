const DEFAULT_LOCALE = 'en';
const DEFAULT_TIMEZONE = 'Asia/Shanghai';

const ENGLISH_PREFIX = 'en';
const CHINESE_LOCALE_SET = new Set(['zh', 'zh-cn', 'zh-hans']);

export const normalizeLocale = (locale?: string | null): 'en' | 'zh-Hans' => {
  if (!locale) {
    return DEFAULT_LOCALE;
  }

  const normalizedLocale = locale.trim().toLowerCase();
  if (normalizedLocale.startsWith(ENGLISH_PREFIX)) {
    return 'en';
  }

  if (CHINESE_LOCALE_SET.has(normalizedLocale)) {
    return 'zh-Hans';
  }

  return normalizedLocale.startsWith('zh') ? 'zh-Hans' : DEFAULT_LOCALE;
};

export const normalizeTimezone = (timezone?: string | null): string => {
  if (!timezone) {
    return DEFAULT_TIMEZONE;
  }

  return timezone.trim() || DEFAULT_TIMEZONE;
};

export const getStoredLocale = (): 'en' | 'zh-Hans' => {
  if (typeof window === 'undefined') {
    return DEFAULT_LOCALE;
  }

  const stored = window.localStorage.getItem('locale');
  if (stored) {
    return normalizeLocale(stored);
  }

  // 首访或 localStorage 被清:回退到浏览器语言,不持久化。
  return normalizeLocale(window.navigator?.language);
};

export const getStoredTimezone = (): string => {
  if (typeof window === 'undefined') {
    return DEFAULT_TIMEZONE;
  }

  return normalizeTimezone(window.localStorage.getItem('timezone'));
};

export const persistLocale = (locale: string) => {
  if (typeof window === 'undefined') {
    return;
  }

  window.localStorage.setItem('locale', normalizeLocale(locale));
};

export const persistTimezone = (timezone: string) => {
  if (typeof window === 'undefined') {
    return;
  }

  window.localStorage.setItem('timezone', normalizeTimezone(timezone));
};

export const DEFAULT_USER_PREFERENCES = {
  locale: DEFAULT_LOCALE as 'en' | 'zh-Hans',
  timezone: DEFAULT_TIMEZONE,
};
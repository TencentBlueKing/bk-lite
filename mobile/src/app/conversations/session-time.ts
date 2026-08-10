import { formatAccountActivity } from '@/platform/preferences/dateTime';

export function formatSessionActivity(
  value: string | undefined,
  locale: string,
  yesterdayLabel: string,
  timezone = 'Asia/Shanghai',
) {
  return value
    ? formatAccountActivity(value, { locale, timezone }, yesterdayLabel)
    : '';
}

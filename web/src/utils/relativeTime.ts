import dayjs from 'dayjs';

type Translate = (
  id: string,
  defaultMessage?: string,
  values?: Record<string, string | number>
) => string;

/** Prefer updated_at, fall back to created_at. */
export function pickEntityTimestamp(
  entity: { updated_at?: string | null; created_at?: string | null }
): string | undefined {
  const value = entity.updated_at || entity.created_at;
  return value ? String(value) : undefined;
}

/** Relative time like「1天前」/「3小时前」. */
export function formatRelativeTime(
  iso: string | null | undefined,
  t?: Translate
): string {
  if (!iso) return '';
  const when = dayjs(iso);
  if (!when.isValid()) return '';

  const seconds = dayjs().diff(when, 'second');
  if (seconds < 5) {
    return t ? t('common.justNow', '刚刚') : '刚刚';
  }
  if (seconds < 60) {
    return t
      ? t('common.secondsAgo', '{count}秒前', { count: seconds })
      : `${seconds}秒前`;
  }
  const mins = Math.floor(seconds / 60);
  if (mins < 60) {
    return t
      ? t('common.minutesAgo', '{count}分钟前', { count: mins })
      : `${mins}分钟前`;
  }
  const hours = Math.floor(mins / 60);
  if (hours < 24) {
    return t
      ? t('common.hoursAgo', '{count}小时前', { count: hours })
      : `${hours}小时前`;
  }
  const days = Math.floor(hours / 24);
  if (days < 30) {
    return t
      ? t('common.daysAgo', '{count}天前', { count: days })
      : `${days}天前`;
  }
  return when.format('YYYY-MM-DD');
}

import { translateForLocale, type OpspilotTranslate } from '@/app/opspilot/components/custom-chat-sse/i18n';

const SECOND_MS = 1000;
const MINUTE_MS = 60 * SECOND_MS;
const HOUR_MS = 60 * MINUTE_MS;

const defaultTranslate = translateForLocale('zh');

const formatSeconds = (milliseconds: number, t: OpspilotTranslate) => {
  const seconds = milliseconds / SECOND_MS;
  const roundedSeconds = Number.isInteger(seconds) ? seconds : Math.round(seconds * 10) / 10;
  const displaySeconds = Math.min(roundedSeconds, 59.9);
  return t('chat.duration.seconds', '{count}秒', { count: displaySeconds });
};

export const formatDurationMs = (value?: number | null, t: OpspilotTranslate = defaultTranslate) => {
  const milliseconds = Math.max(0, Math.floor(Number(value) || 0));
  if (milliseconds < SECOND_MS) {
    return `${milliseconds}ms`;
  }
  if (milliseconds < MINUTE_MS) {
    return formatSeconds(milliseconds, t);
  }

  const hours = Math.floor(milliseconds / HOUR_MS);
  const minutes = Math.floor((milliseconds % HOUR_MS) / MINUTE_MS);
  const seconds = Math.floor((milliseconds % MINUTE_MS) / SECOND_MS);
  const parts: string[] = [];

  if (hours) {
    parts.push(t('chat.duration.hours', '{count}小时', { count: hours }));
  }
  if (minutes) {
    parts.push(t('chat.duration.minutes', '{count}分钟', { count: minutes }));
  }
  if (seconds) {
    parts.push(t('chat.duration.seconds', '{count}秒', { count: seconds }));
  }

  return parts.join('') || '0ms';
};

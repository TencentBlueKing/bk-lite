const SECOND_MS = 1000;
const MINUTE_MS = 60 * SECOND_MS;
const HOUR_MS = 60 * MINUTE_MS;

const formatSeconds = (milliseconds: number) => {
  const seconds = milliseconds / SECOND_MS;
  const roundedSeconds = Number.isInteger(seconds) ? seconds : Math.round(seconds * 10) / 10;
  const displaySeconds = Math.min(roundedSeconds, 59.9);
  return `${displaySeconds}秒`;
};

export const formatDurationMs = (value?: number | null) => {
  const milliseconds = Math.max(0, Math.floor(Number(value) || 0));
  if (milliseconds < SECOND_MS) {
    return `${milliseconds}ms`;
  }
  if (milliseconds < MINUTE_MS) {
    return formatSeconds(milliseconds);
  }

  const hours = Math.floor(milliseconds / HOUR_MS);
  const minutes = Math.floor((milliseconds % HOUR_MS) / MINUTE_MS);
  const seconds = Math.floor((milliseconds % MINUTE_MS) / SECOND_MS);
  const parts: string[] = [];

  if (hours) {
    parts.push(`${hours}小时`);
  }
  if (minutes) {
    parts.push(`${minutes}分钟`);
  }
  if (seconds) {
    parts.push(`${seconds}秒`);
  }

  return parts.join('') || '0ms';
};

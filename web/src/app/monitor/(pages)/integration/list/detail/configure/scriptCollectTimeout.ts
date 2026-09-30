export const SCRIPT_MIN_INTERVAL_SECONDS = 60;
export const SCRIPT_DETECT_TIMEOUT_MARGIN_SECONDS = 10;

export const parseScriptDurationSeconds = (value: unknown): number | null => {
  if (value == null || value === '') {
    return null;
  }
  if (typeof value === 'boolean') {
    return null;
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    return Math.trunc(value);
  }
  const text = String(value).trim();
  if (!text) {
    return null;
  }
  const withUnit = text.match(/^(-?\d+)s$/i);
  if (withUnit) {
    return Number(withUnit[1]);
  }
  if (/^-?\d+$/.test(text)) {
    return Number(text);
  }
  const numeric = Number(text);
  if (!Number.isFinite(numeric)) {
    return null;
  }
  return Math.trunc(numeric);
};

export const defaultScriptTimeoutSeconds = (intervalSeconds: number): number =>
  Math.max(1, Math.trunc(intervalSeconds) - 1);

export const resolveScriptTimeoutSeconds = (
  timeout: unknown,
  interval: unknown
): number => {
  const intervalSeconds =
    parseScriptDurationSeconds(interval) ?? SCRIPT_MIN_INTERVAL_SECONDS;
  const timeoutSeconds = parseScriptDurationSeconds(timeout);
  if (timeoutSeconds == null || timeoutSeconds <= 0) {
    return defaultScriptTimeoutSeconds(intervalSeconds);
  }
  return timeoutSeconds;
};

export const shouldEmitScriptTimeout = (
  timeout: unknown,
  interval: unknown
): boolean => {
  const intervalSeconds = parseScriptDurationSeconds(interval);
  const timeoutSeconds = parseScriptDurationSeconds(timeout);
  if (intervalSeconds == null || timeoutSeconds == null || timeoutSeconds < 1) {
    return false;
  }
  return timeoutSeconds !== defaultScriptTimeoutSeconds(intervalSeconds);
};

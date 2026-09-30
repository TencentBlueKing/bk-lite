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

export const scriptTimeoutFromInterval = (interval: unknown): number =>
  defaultScriptTimeoutSeconds(
    parseScriptDurationSeconds(interval) ?? SCRIPT_MIN_INTERVAL_SECONDS
  );

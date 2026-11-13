const encodeToken = (text: string): string => text.replace(/%/g, '%25').replace(/:/g, '%3A');

export const encodeCollectedTag = (key: string, value: string): string => `${encodeToken(key)}:${encodeToken(value)}`;

const decodeToken = (text: string): string => {
  try {
    return decodeURIComponent(text).trim();
  } catch {
    return text.trim();
  }
};

export const decodeCollectedTag = (raw: string): { key: string; value: string } | null => {
  const text = raw.trim();
  const index = text.indexOf(':');
  if (index <= 0) return null;
  const key = decodeToken(text.slice(0, index));
  const value = decodeToken(text.slice(index + 1));
  if (!key) return null;
  return { key, value };
};

export const displayCollectedTag = (raw: string): string => {
  const parsed = decodeCollectedTag(raw);
  if (!parsed || !raw.includes('%')) return raw.trim();
  return `${parsed.key}:${parsed.value}`;
};

const TAG_COLOR_PRESETS = [
  'magenta',
  'red',
  'volcano',
  'orange',
  'gold',
  'lime',
  'green',
  'cyan',
  'blue',
  'geekblue',
  'purple',
] as const;

const normalizeTagText = (value: unknown): string => {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value.trim();
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>;
    const candidate = record.value ?? record.label ?? record.name ?? record.key;
    if (candidate !== undefined && candidate !== null) {
      return String(candidate).trim();
    }
  }
  return String(value).trim();
};

const parseJsonArray = (value: string): unknown[] | null => {
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
};

export const normalizeTagValues = (value: unknown): string[] => {
  if (Array.isArray(value)) {
    return value
      .map((item) => normalizeTagText(item))
      .filter(Boolean);
  }

  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed) return [];

    if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
      const parsed = parseJsonArray(trimmed);
      if (parsed) {
        return normalizeTagValues(parsed);
      }
    }

    return [trimmed];
  }

  const normalized = normalizeTagText(value);
  return normalized ? [normalized] : [];
};

export const getTagDisplayText = (value: unknown): string => {
  const values = normalizeTagValues(value);
  return values.length ? values.join('，') : '--';
};

export const getTagColorByLabel = (label: string): string => {
  const normalized = label.trim().toLowerCase();
  if (!normalized) return TAG_COLOR_PRESETS[0];

  let hash = 2166136261;
  for (let i = 0; i < normalized.length; i++) {
    hash ^= normalized.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }

  return TAG_COLOR_PRESETS[(hash >>> 0) % TAG_COLOR_PRESETS.length];
};

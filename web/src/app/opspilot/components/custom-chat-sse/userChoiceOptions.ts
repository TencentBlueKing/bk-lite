import { UserChoiceOption, UserChoiceRequest } from '../../types/global';

function asText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

export function normalizeUserChoiceOptions(options: unknown): UserChoiceOption[] {
  if (!Array.isArray(options)) {
    return [];
  }
  const normalized: UserChoiceOption[] = [];
  const seen = new Set<string>();
  for (const item of options) {
    if (typeof item === 'string') {
      const key = item.trim();
      if (!key || seen.has(key)) {
        continue;
      }
      seen.add(key);
      normalized.push({ key, label: key });
      continue;
    }
    if (!item || typeof item !== 'object') {
      continue;
    }
    const record = item as Record<string, unknown>;
    const key = asText(record.key) || asText(record.value) || asText(record.name);
    const label = asText(record.label) || asText(record.display_name) || key;
    if (!key || seen.has(key)) {
      continue;
    }
    seen.add(key);
    normalized.push({
      key,
      label,
      description: asText(record.description) || undefined,
      icon: asText(record.icon) || undefined,
      disabled: Boolean(record.disabled),
      recommended: Boolean(record.recommended),
    });
  }
  return normalized;
}

export function isUserChoiceRequestClosed(
  status: UserChoiceRequest['status'] | undefined,
): boolean {
  return status === 'submitted' || status === 'timeout';
}

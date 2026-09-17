const INTERNAL_RESULT_KEYS = new Set(['id']);

const LOGICAL_FIELD_ALIASES: Record<string, string> = {
  _time: 'timestamp',
  _msg: 'message'
};

export const mergeSearchResultFields = (
  catalogFields: string[],
  rows: Array<Record<string, unknown>>
): string[] => {
  const merged = new Set(catalogFields);

  for (const row of rows) {
    for (const key of Object.keys(row)) {
      if (INTERNAL_RESULT_KEYS.has(key)) {
        continue;
      }
      merged.add(LOGICAL_FIELD_ALIASES[key] ?? key);
    }
  }

  return [...merged].sort((left, right) => left.localeCompare(right));
};

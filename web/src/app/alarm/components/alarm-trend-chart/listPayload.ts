export function extractAlarmListItems<T>(payload: unknown): T[] {
  if (Array.isArray(payload)) {
    return payload as T[];
  }
  if (payload && typeof payload === 'object') {
    const record = payload as { items?: unknown; results?: unknown };
    if (Array.isArray(record.items)) {
      return record.items as T[];
    }
    if (Array.isArray(record.results)) {
      return record.results as T[];
    }
  }
  return [];
}

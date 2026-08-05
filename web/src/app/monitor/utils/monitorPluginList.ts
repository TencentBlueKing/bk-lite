/** 兼容 monitor_plugin list:全量数组 或 分页 {count, items} */
export function unwrapMonitorPluginList<T = any>(data: unknown): T[] {
  if (Array.isArray(data)) {
    return data as T[];
  }
  if (data && typeof data === 'object') {
    const record = data as { items?: unknown; results?: unknown };
    if (Array.isArray(record.items)) {
      return record.items as T[];
    }
    if (Array.isArray(record.results)) {
      return record.results as T[];
    }
  }
  return [];
}

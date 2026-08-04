/**
 * 从 monitor_object 列表里解析 Process 对象 id。
 */
export function resolveProcessObjectId(data: unknown): string {
  const list = Array.isArray(data)
    ? data
    : (data as { items?: unknown[]; results?: unknown[] })?.items ||
      (data as { results?: unknown[] })?.results ||
      [];
  const processObj = (
    list as Array<{ name?: string; id?: string | number }>
  ).find((item) => item?.name === 'Process');
  return processObj?.id != null ? String(processObj.id) : '';
}

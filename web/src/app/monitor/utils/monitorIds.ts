/**
 * 监控模块 id 边界工具。
 *
 * URL / useSearchParams / Tree key 多为 string，API 实体 id 多为 number。
 * 严格 === 会在升级后静默匹配失败；统一用字符串比较。
 */

/** 规范化为字符串；空值返回 ''。接受 unknown 以兼容 React.Key / API 混用。 */
export const toMonitorIdString = (id: unknown): string => {
  if (id == null || id === '') return '';
  return String(id);
};

/** 判断两个 id 是否表示同一实体（忽略 number/string 差异） */
export const sameMonitorId = (a: unknown, b: unknown): boolean => {
  const left = toMonitorIdString(a);
  const right = toMonitorIdString(b);
  if (!left || !right) return left === right;
  return left === right;
};

/** 在列表中按 id 查找（兼容 number | string） */
export const findByMonitorId = <T extends { id?: unknown }>(
  items: T[] | null | undefined,
  id: unknown
): T | undefined => {
  if (!items?.length || id == null || id === '') return undefined;
  return items.find((item) => sameMonitorId(item.id, id));
};

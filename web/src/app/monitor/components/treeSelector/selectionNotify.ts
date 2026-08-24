/**
 * 对象树是否需要把选中节点通知给父页面。
 *
 * 点击叶子后父页面会把 objId 写回 URL，TreeSelector 再收到同一个
 * defaultSelectedKey。若此时再次 onNodeSelect，父页面会 abort 刚发出的
 * 列表请求，右侧插件/资产停在上一份数据。
 */
export const shouldNotifyTreeNodeSelect = (
  lastNotifiedKey: string,
  nextKey: unknown
): boolean => {
  const normalized = String(nextKey ?? '').trim();
  if (!normalized) return false;
  return lastNotifiedKey !== normalized;
};

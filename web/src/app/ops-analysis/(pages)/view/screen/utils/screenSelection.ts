/** 再次选中当前组件（拖动、缩放、点按已选项）不是切换数据配置目标。 */
export const isSameScreenDataTarget = (
  currentItemId: string | null,
  nextItemId: string | null,
): boolean => nextItemId != null && nextItemId === currentItemId;

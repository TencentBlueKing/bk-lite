export interface DirectoryEditCollapse {
  collapsed: boolean;
  /** 进入本次编辑前的目录状态。null 表示没有待恢复的编辑收起。 */
  savedCollapsed: boolean | null;
}

/** 编辑大屏时收起目录，结束编辑后恢复进入前的状态。 */
export function applyDirectoryEditCollapse(
  state: DirectoryEditCollapse,
  editing: boolean,
): DirectoryEditCollapse {
  if (editing) {
    if (state.savedCollapsed !== null) {
      return { collapsed: true, savedCollapsed: state.savedCollapsed };
    }
    return { collapsed: true, savedCollapsed: state.collapsed };
  }
  if (state.savedCollapsed === null) {
    return state;
  }
  return { collapsed: state.savedCollapsed, savedCollapsed: null };
}

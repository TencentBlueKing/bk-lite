import { describe, expect, it } from 'vitest';
import { applyDirectoryEditCollapse } from '../directoryEditCollapse';

describe('applyDirectoryEditCollapse', () => {
  it('收起展开中的目录，并在结束编辑后展开', () => {
    const editing = applyDirectoryEditCollapse(
      { collapsed: false, savedCollapsed: null },
      true,
    );
    expect(editing).toEqual({ collapsed: true, savedCollapsed: false });

    expect(applyDirectoryEditCollapse(editing, false)).toEqual({
      collapsed: false,
      savedCollapsed: null,
    });
  });

  it('编辑前已收起时，结束后仍保持收起', () => {
    const editing = applyDirectoryEditCollapse(
      { collapsed: true, savedCollapsed: null },
      true,
    );
    expect(editing).toEqual({ collapsed: true, savedCollapsed: true });
    expect(applyDirectoryEditCollapse(editing, false)).toEqual({
      collapsed: true,
      savedCollapsed: null,
    });
  });

  it('重复进入编辑不会覆盖最初记住的状态', () => {
    const editing = applyDirectoryEditCollapse(
      { collapsed: false, savedCollapsed: null },
      true,
    );
    const toggled = { ...editing, collapsed: false };
    expect(applyDirectoryEditCollapse(toggled, true)).toEqual({
      collapsed: true,
      savedCollapsed: false,
    });
  });
});

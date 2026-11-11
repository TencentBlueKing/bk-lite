import { describe, expect, it } from 'vitest';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';
import {
  filterTreeNode,
  getAncestorKeys,
  getSearchExpandedKeys,
  getSelectableLeafKeys,
  resolveLeftExpandedKeys,
  resolveRoleTreeLabel,
} from '@/app/system-manager/utils/roleTreeUtils';

const guestTree: TreeDataNode[] = [
  {
    key: 'root-a',
    title: 'Default',
    children: [{ key: 'a-1', title: 'a-1' }],
  },
  {
    key: 'guest',
    title: 'Guest',
    children: Array.from({ length: 8 }, (_, index) => ({
      key: `guest-${index}`,
      title: `guest-${index}`,
    })),
  },
];

describe('getAncestorKeys', () => {
  it('returns no keys when nothing is selected, so a long sibling list stays collapsed', () => {
    expect(getAncestorKeys(guestTree, [])).toEqual([]);
  });

  it('expands only ancestors of the selected node, not the node or its siblings', () => {
    expect(getAncestorKeys(guestTree, ['guest-3'])).toEqual(['guest']);
  });

  it('keeps a selected root collapsed so its children are not painted', () => {
    expect(getAncestorKeys(guestTree, ['guest'])).toEqual([]);
  });
});

describe('resolveLeftExpandedKeys', () => {
  it('applies ancestor defaults when edit selection arrives after an empty first paint', () => {
    // RoleTransfer 编辑态用 loading 卸挂保证只走这一次；helper 仍须在首次调用时按选中项展开祖先。
    const afterEmptyPaint = resolveLeftExpandedKeys({
      searchValue: '',
      mode: 'group',
      treeData: guestTree,
      selectedKeys: [],
      prevExpandedKeys: [],
      keysBeforeSearch: null,
      userHasExpanded: false,
    });
    expect(afterEmptyPaint.expandedKeys).toEqual([]);

    const afterDetail = resolveLeftExpandedKeys({
      searchValue: '',
      mode: 'group',
      treeData: guestTree,
      selectedKeys: ['guest-3'],
      prevExpandedKeys: afterEmptyPaint.expandedKeys,
      keysBeforeSearch: null,
      userHasExpanded: false,
    });
    expect(afterDetail.expandedKeys).toEqual(['guest']);
  });

  it('keeps a user-expanded Guest when the selection later changes', () => {
    const result = resolveLeftExpandedKeys({
      searchValue: '',
      mode: 'group',
      treeData: guestTree,
      selectedKeys: ['root-a'],
      prevExpandedKeys: ['guest'],
      keysBeforeSearch: null,
      userHasExpanded: true,
    });
    expect(result.expandedKeys).toEqual(['guest']);
  });

  it('restores keys from before search instead of leaving search matches expanded', () => {
    const whileSearching = resolveLeftExpandedKeys({
      searchValue: 'guest-3',
      mode: 'group',
      treeData: guestTree,
      selectedKeys: [],
      prevExpandedKeys: [],
      keysBeforeSearch: null,
      userHasExpanded: false,
    });
    expect(whileSearching.expandedKeys).toEqual(['guest']);
    expect(whileSearching.keysBeforeSearch).toEqual([]);

    const afterClear = resolveLeftExpandedKeys({
      searchValue: '',
      mode: 'group',
      treeData: guestTree,
      selectedKeys: [],
      prevExpandedKeys: whileSearching.expandedKeys,
      keysBeforeSearch: whileSearching.keysBeforeSearch,
      userHasExpanded: false,
    });
    expect(afterClear.expandedKeys).toEqual([]);
    expect(afterClear.keysBeforeSearch).toBeNull();
  });
});

const roleTree: TreeDataNode & { display_name?: string } = {
  key: 9746,
  title: 'system-manager',
  display_name: '系统管理',
  selectable: false,
  children: [
    { key: 1, title: 'admin', selectable: true },
    { key: 2, title: 'normal', selectable: true },
  ],
};

const zhApp = (id: string, fallback?: string) => (id === 'apps.system-manager' ? '系统管理' : fallback || id);
const enApp = (id: string, fallback?: string) => {
  if (id === 'apps.system-manager') return 'System Management';
  if (id === 'apps.monitor') return 'Monitor Center';
  if (id === 'apps.ops-console') return 'Console';
  return fallback || id;
};

const monitorTree: TreeDataNode & { display_name?: string } = {
  key: 886,
  title: 'monitor',
  display_name: '监控中心',
  selectable: false,
  children: [
    { key: 3, title: 'admin', selectable: true },
    { key: 4, title: 'normal', selectable: true },
  ],
};

describe('filterTreeNode', () => {
  it('keeps every role when the visible app name matches', () => {
    const matched = filterTreeNode(roleTree, '系统管理', zhApp);
    expect(matched?.children?.map((child) => child.key)).toEqual([1, 2]);
  });

  it('keeps every role when the English app name matches', () => {
    const matched = filterTreeNode(monitorTree, 'Monitor Center', enApp);
    expect(matched?.children?.map((child) => child.key)).toEqual([3, 4]);
  });

  it('keeps every role when the app id matches', () => {
    const matched = filterTreeNode(roleTree, 'system-manager');
    expect(matched?.children?.map((child) => child.key)).toEqual([1, 2]);
  });

  it('keeps only the role whose name matches', () => {
    const matched = filterTreeNode(roleTree, 'admin', enApp);
    expect(matched?.key).toBe(9746);
    expect(matched?.children?.map((child) => child.key)).toEqual([1]);
  });

  it('does not match a stored name that is not on screen', () => {
    expect(filterTreeNode(monitorTree, '监控中心', enApp)).toBeNull();
  });

  it('drops an app whose visible name and id both miss', () => {
    expect(filterTreeNode(roleTree, '控制台', zhApp)).toBeNull();
  });
});

describe('getSearchExpandedKeys', () => {
  it('expands an app matched by its visible name', () => {
    expect(getSearchExpandedKeys([roleTree], '系统管理', zhApp)).toEqual([9746]);
  });

  it('expands an app matched by its English name', () => {
    expect(getSearchExpandedKeys([monitorTree], 'Monitor Center', enApp)).toEqual([886]);
  });
});

describe('getSelectableLeafKeys', () => {
  it('returns role ids under an app and ignores the app container key', () => {
    expect(getSelectableLeafKeys(roleTree)).toEqual([1, 2]);
  });

  it('returns nothing when search has removed the roles and only the app container remains', () => {
    expect(getSelectableLeafKeys({ ...roleTree, children: [] })).toEqual([]);
  });
});

describe('resolveRoleTreeLabel', () => {
  const t = (id: string, fallback?: string) => (id === 'apps.system-manager' ? 'System Management' : fallback || id);

  it('translates a built-in app by its id', () => {
    expect(resolveRoleTreeLabel(roleTree, t)).toBe('System Management');
  });

  it('keeps a role name', () => {
    expect(resolveRoleTreeLabel({ key: 1, title: 'admin', selectable: true }, t)).toBe('admin');
  });
});

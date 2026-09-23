import { describe, expect, it } from 'vitest';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';
import { getAncestorKeys, resolveLeftExpandedKeys } from '@/app/system-manager/utils/roleTreeUtils';

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

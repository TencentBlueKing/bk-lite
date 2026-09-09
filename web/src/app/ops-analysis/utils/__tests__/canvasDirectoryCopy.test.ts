import { describe, expect, it } from 'vitest';

import type { DirItem } from '@/app/ops-analysis/types';
import {
  buildCopyDirectoryTree,
  collectDirectoryChainGroupIds,
  collectDirectoryExpandKeys,
  convergeCopyGroups,
  defaultCopyGroups,
  filterGroupTreeByAllowedIds,
  getSidebarCanvasMenuKeys,
  shouldShowCanvasCopyAction,
} from '../canvasDirectoryCopy';

const tree: DirItem[] = [
  {
    id: 'directory_1',
    data_id: '1',
    name: '根目录',
    type: 'directory',
    groups: [1, 2, 3],
    children: [
      {
        id: 'directory_2',
        data_id: '2',
        name: '子目录',
        type: 'directory',
        groups: [1, 2],
        children: [
          {
            id: 'dashboard_9',
            data_id: '9',
            name: '运营盘',
            type: 'dashboard',
            groups: [1],
          },
        ],
      },
      {
        id: 'directory_3',
        data_id: '3',
        name: '内置目录',
        type: 'directory',
        is_build_in: true,
        groups: [1],
        children: [
          {
            id: 'directory_4',
            data_id: '4',
            name: '内置下的用户目录',
            type: 'directory',
            groups: [1],
          },
        ],
      },
    ],
  },
];

describe('canvas copy menu', () => {
  it('offers copy on ordinary and builtin canvases, not directories', () => {
    expect(shouldShowCanvasCopyAction({ type: 'dashboard' })).toBe(true);
    expect(shouldShowCanvasCopyAction({ type: 'networkTopology' })).toBe(true);
    expect(shouldShowCanvasCopyAction({ type: 'directory' })).toBe(false);
    expect(getSidebarCanvasMenuKeys({ type: 'dashboard' })).toEqual([
      'edit',
      'delete',
      'copy',
      'export',
    ]);
    expect(getSidebarCanvasMenuKeys({ type: 'dashboard', is_build_in: true })).toEqual([
      'copy',
      'export',
      'edit',
      'delete',
    ]);
    expect(getSidebarCanvasMenuKeys({ type: 'directory' })).toEqual([]);
  });
});

describe('copy directory tree', () => {
  it('keeps directory structure, omits builtin targets, and ignores canvases', () => {
    const options = buildCopyDirectoryTree(tree);
    expect(options).toEqual([
      {
        title: '根目录',
        value: 1,
        key: 1,
        disabled: false,
        children: [
          {
            title: '子目录',
            value: 2,
            key: 2,
            disabled: false,
          },
          {
            title: '内置下的用户目录',
            value: 4,
            key: 4,
            disabled: false,
          },
        ],
      },
    ]);
  });
});

describe('directory chain groups', () => {
  it('intersects groups along the directory chain', () => {
    expect(collectDirectoryChainGroupIds(tree, 2)).toEqual([1, 2]);
    expect(collectDirectoryExpandKeys(tree, 2)).toEqual(['directory_1', 'directory_2']);
  });
});

describe('copy groups defaults', () => {
  it('defaults to the current org when it is allowed, then converges on directory switch', () => {
    expect(defaultCopyGroups([1, 2], 1)).toEqual([1]);
    expect(defaultCopyGroups([2, 3], 1)).toEqual([]);
    expect(convergeCopyGroups([1, 8], [2, 3], 2)).toEqual([2]);
    expect(convergeCopyGroups([2], [2, 3], 1)).toEqual([2]);
  });
});

describe('filter group tree', () => {
  it('keeps allowed orgs and disables ancestors that are only structural', () => {
    const filtered = filterGroupTreeByAllowedIds(
      [
        {
          title: '集团',
          value: 10,
          key: 10,
          children: [
            { title: '允许', value: 1, key: 1 },
            { title: '越界', value: 99, key: 99 },
          ],
        },
      ],
      [1],
    );
    expect(filtered).toEqual([
      {
        title: '集团',
        value: 10,
        key: 10,
        disabled: true,
        children: [{ title: '允许', value: 1, key: 1, disabled: false }],
      },
    ]);
  });
});

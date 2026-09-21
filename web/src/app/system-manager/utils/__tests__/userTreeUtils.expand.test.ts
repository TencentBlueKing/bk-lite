import { describe, expect, it } from 'vitest';
import {
  collectExpandableKeys,
  type ExtendedTreeDataNode,
} from '@/app/system-manager/utils/userTreeUtils';

const tree: ExtendedTreeDataNode[] = [
  {
    key: 'default',
    title: 'Default',
    children: [
      { key: 'sub-a', title: 'Sub A' },
      {
        key: 'sub-b',
        title: 'Sub B',
        children: [
          { key: 'leaf-b1', title: 'Leaf B1' },
        ],
      },
    ],
  },
  {
    key: 'guest',
    title: 'Guest',
    children: [{ key: 'lmr', title: 'Lmr' }],
  },
  { key: 'local', title: '本地组织' },
];

describe('collectExpandableKeys', () => {
  it('returns every node that still has children', () => {
    expect(collectExpandableKeys(tree)).toEqual(['default', 'sub-b', 'guest']);
  });
});

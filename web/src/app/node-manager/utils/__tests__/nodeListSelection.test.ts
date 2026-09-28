import { describe, expect, it } from 'vitest';
import {
  nextSelectedNodeMap,
  selectedNodesFromMap,
  shouldClearNodeSelection
} from '../nodeListSelection';

const page1 = [
  { key: 'a', id: 'a', operating_system: 'linux', cpu_architecture: 'x86_64' },
  { key: 'b', id: 'b', operating_system: 'linux', cpu_architecture: 'x86_64' }
];
const page2 = [
  { key: 'c', id: 'c', operating_system: 'windows', cpu_architecture: 'x86_64' }
];

describe('nextSelectedNodeMap', () => {
  it('keeps previous page snapshots when selecting more keys', () => {
    const afterPage1 = nextSelectedNodeMap({
      previous: new Map(),
      selectedKeys: ['a'],
      currentPageRows: page1
    });
    const afterPage2 = nextSelectedNodeMap({
      previous: afterPage1,
      selectedKeys: ['a', 'c'],
      currentPageRows: page2
    });
    expect(afterPage2.get('a')?.operating_system).toBe('linux');
    expect(afterPage2.get('c')?.operating_system).toBe('windows');
  });

  it('drops snapshots for unselected keys', () => {
    const previous = nextSelectedNodeMap({
      previous: new Map(),
      selectedKeys: ['a', 'b'],
      currentPageRows: page1
    });
    const next = nextSelectedNodeMap({
      previous,
      selectedKeys: ['b'],
      currentPageRows: page1
    });
    expect([...next.keys()]).toEqual(['b']);
  });
});

describe('shouldClearNodeSelection', () => {
  it('clears when filters, unassigned scope, or cloud region change', () => {
    expect(shouldClearNodeSelection({ reason: 'filters' })).toBe(true);
    expect(shouldClearNodeSelection({ reason: 'unassigned' })).toBe(true);
    expect(shouldClearNodeSelection({ reason: 'cloudRegion' })).toBe(true);
    expect(shouldClearNodeSelection({ reason: 'pagination' })).toBe(false);
  });
});

describe('selectedNodesFromMap', () => {
  it('returns rows in key order', () => {
    const map = nextSelectedNodeMap({
      previous: new Map(),
      selectedKeys: ['a', 'b'],
      currentPageRows: page1
    });
    const nodes = selectedNodesFromMap(['b', 'a'], map);
    expect(nodes.map((item) => item.key)).toEqual(['b', 'a']);
  });
});

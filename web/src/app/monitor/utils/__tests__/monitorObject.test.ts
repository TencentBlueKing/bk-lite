import { describe, expect, it } from 'vitest';
import { ObjectItem } from '@/app/monitor/types';
import { filterVisibleMonitorObjects } from '@/app/monitor/utils/monitorObject';

const object = (
  overrides: Partial<ObjectItem> & Pick<ObjectItem, 'id' | 'name'>
): ObjectItem =>
  ({
    type: 'K3S',
    description: '',
    is_visible: true,
    parent: null,
    ...overrides
  }) as ObjectItem;

describe('filterVisibleMonitorObjects', () => {
  it('hides child objects when the parent is invisible', () => {
    const parent = object({ id: 1, name: 'K3SCluster', is_visible: false });
    const pod = object({ id: 2, name: 'K3SPod', parent: 1 });
    const node = object({ id: 3, name: 'K3SNode', parent: 1 });
    const other = object({ id: 4, name: 'Host', type: 'OS' });

    expect(
      filterVisibleMonitorObjects([parent, pod, node, other]).map((item) => item.name)
    ).toEqual(['Host']);
  });

  it('hides nested descendants of an invisible parent', () => {
    const parent = object({ id: 1, name: 'Parent', is_visible: false });
    const child = object({ id: 2, name: 'Child', parent: 1 });
    const grandchild = object({ id: 3, name: 'Grandchild', parent: 2 });

    expect(filterVisibleMonitorObjects([parent, child, grandchild])).toEqual([]);
  });

  it('keeps visible parents and their visible children', () => {
    const parent = object({ id: 1, name: 'K3SCluster' });
    const pod = object({ id: 2, name: 'K3SPod', parent: 1 });

    expect(
      filterVisibleMonitorObjects([parent, pod]).map((item) => item.name)
    ).toEqual(['K3SCluster', 'K3SPod']);
  });
});

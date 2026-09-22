import { describe, expect, it } from 'vitest';

import {
  K8S_VIEW_NODE_MEM_ORDERING,
  K8S_VIEW_POD_CPU_ORDERING,
  K8S_VIEW_POD_MEM_ORDERING,
  buildK8sClusterViewListHref,
  resolveMonitorObjectIdByName,
} from '../view-list-link';

describe('resolveMonitorObjectIdByName', () => {
  it('parses Pod and Node ids from an object list', () => {
    const objects = [
      { name: 'Host', id: 1 },
      { name: 'Pod', id: 42 },
      { name: 'Node', id: '7' },
    ];
    expect(resolveMonitorObjectIdByName(objects, 'Pod')).toBe('42');
    expect(resolveMonitorObjectIdByName(objects, 'Node')).toBe('7');
    expect(resolveMonitorObjectIdByName(objects, 'K3SPod')).toBe('');
  });

  it('returns empty when the payload is not an array', () => {
    expect(
      resolveMonitorObjectIdByName(
        { items: [{ name: 'Pod', id: 9 }], results: [{ name: 'Pod', id: 8 }] },
        'Pod'
      )
    ).toBe('');
    expect(resolveMonitorObjectIdByName(null, 'Pod')).toBe('');
    expect(resolveMonitorObjectIdByName(undefined, 'Node')).toBe('');
  });
});

describe('buildK8sClusterViewListHref', () => {
  it('builds a cluster-filtered list href with CPU/memory sort', () => {
    expect(
      buildK8sClusterViewListHref({
        objectId: '42',
        clusterInstanceId: 'cluster-a',
        ordering: K8S_VIEW_POD_CPU_ORDERING,
      })
    ).toBe(
      '/monitor/view?object_id=42&vm_params.instance_id=cluster-a&ordering=K8S%3A%3Apod_cpu_utilization&order=desc'
    );
    expect(
      buildK8sClusterViewListHref({
        objectId: '42',
        clusterInstanceId: 'cluster-a',
        ordering: K8S_VIEW_POD_MEM_ORDERING,
      })
    ).toContain('ordering=K8S%3A%3Apod_memory_utilization');
    expect(
      buildK8sClusterViewListHref({
        objectId: '7',
        clusterInstanceId: 'cluster-a',
        ordering: K8S_VIEW_NODE_MEM_ORDERING,
      })
    ).toContain('ordering=K8S%3A%3Anode_memory_utilization');
  });

  it('omits sort for restart Top and returns null without ids', () => {
    expect(
      buildK8sClusterViewListHref({
        objectId: '42',
        clusterInstanceId: 'cluster-a',
      })
    ).toBe('/monitor/view?object_id=42&vm_params.instance_id=cluster-a');
    expect(
      buildK8sClusterViewListHref({
        objectId: '',
        clusterInstanceId: 'cluster-a',
      })
    ).toBeNull();
    expect(
      buildK8sClusterViewListHref({
        objectId: '42',
        clusterInstanceId: '  ',
      })
    ).toBeNull();
  });
});

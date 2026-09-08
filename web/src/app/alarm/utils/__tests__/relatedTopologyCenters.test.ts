import { describe, expect, it } from 'vitest';
import { listRelatedTopologyCenters, resolveRelatedTopologyTabVisibility } from '../relatedTopologyCenters';

describe('listRelatedTopologyCenters', () => {
  it('returns nothing when every cmdb_id is empty', () => {
    expect(
      listRelatedTopologyCenters([
        {
          monitor_id: 'm1',
          cmdb_id: null,
          resource_type: 'host',
          resource_name: 'vm-01',
        },
        {
          monitor_id: 'm2',
          cmdb_id: '  ',
          resource_type: 'host',
          resource_name: 'vm-02',
        },
      ]),
    ).toEqual([]);
  });

  it('keeps snapshot order, skips objects without cmdb_id, and dedupes', () => {
    expect(
      listRelatedTopologyCenters([
        {
          monitor_id: 'm1',
          cmdb_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
          resource_type: 'host',
          resource_name: 'vm-01',
        },
        {
          monitor_id: 'm2',
          cmdb_id: null,
          resource_type: 'switch',
          resource_name: 'sw-01',
        },
        {
          monitor_id: 'm3',
          cmdb_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
          resource_type: 'host',
          resource_name: 'vm-01-dup',
        },
        {
          monitor_id: 'm4',
          cmdb_id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
          resource_type: 'router',
          resource_name: 'r-01',
        },
      ]),
    ).toEqual([
      {
        instUuid: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        label: 'host：vm-01',
      },
      {
        instUuid: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
        label: 'router：r-01',
      },
    ]);
  });
});

describe('resolveRelatedTopologyTabVisibility', () => {
  it('hides when undeclared, unbound, unique denied, or unique still pending', () => {
    expect(
      resolveRelatedTopologyTabVisibility({
        declared: false,
        centerCount: 1,
        uniqueAccess: 'ok',
      }),
    ).toBe(false);
    expect(
      resolveRelatedTopologyTabVisibility({
        declared: true,
        centerCount: 0,
        uniqueAccess: 'ok',
      }),
    ).toBe(false);
    expect(
      resolveRelatedTopologyTabVisibility({
        declared: true,
        centerCount: 1,
        uniqueAccess: 'hidden',
      }),
    ).toBe(false);
    expect(
      resolveRelatedTopologyTabVisibility({
        declared: true,
        centerCount: 1,
        uniqueAccess: 'pending',
      }),
    ).toBe(false);
  });

  it('shows for unique ok/retryable and for multiple centers even if one would fail', () => {
    expect(
      resolveRelatedTopologyTabVisibility({
        declared: true,
        centerCount: 1,
        uniqueAccess: 'ok',
      }),
    ).toBe(true);
    expect(
      resolveRelatedTopologyTabVisibility({
        declared: true,
        centerCount: 1,
        uniqueAccess: 'retryable',
      }),
    ).toBe(true);
    expect(
      resolveRelatedTopologyTabVisibility({
        declared: true,
        centerCount: 2,
        uniqueAccess: 'hidden',
      }),
    ).toBe(true);
  });
});

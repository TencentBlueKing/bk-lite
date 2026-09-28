import { describe, expect, it } from 'vitest';
import {
  buildNodeExportRequest,
  parseContentDispositionFilename
} from '../nodeListExport';

const filters = { active: [{ lookup_expr: 'in', value: ['false'] }] };

describe('buildNodeExportRequest', () => {
  it('selected scope sends selected ids and skips filters', () => {
    const result = buildNodeExportRequest({
      scope: 'selected',
      selectedIds: ['a', 'b'],
      currentPageIds: ['page-1'],
      cloudRegionId: 3,
      filters: { name: [{ lookup_expr: 'icontains', value: 'x' }] },
      unassignedOnly: true
    });
    expect(result.empty).toBe(false);
    expect(result.query).toEqual({ unassigned: true });
    expect(result.body).toEqual({
      cloud_region_id: 3,
      selected_ids: ['a', 'b']
    });
    expect(result.body?.filters).toBeUndefined();
  });

  it('currentPage scope sends page ids and ignores selected ids', () => {
    const result = buildNodeExportRequest({
      scope: 'currentPage',
      selectedIds: ['a', 'b'],
      currentPageIds: ['page-1', 'page-2'],
      cloudRegionId: 3,
      filters,
      unassignedOnly: false
    });
    expect(result.empty).toBe(false);
    expect(result.body).toEqual({
      cloud_region_id: 3,
      selected_ids: ['page-1', 'page-2']
    });
    expect(result.body?.filters).toBeUndefined();
  });

  it('all scope sends filters and ignores selected ids', () => {
    const result = buildNodeExportRequest({
      scope: 'all',
      selectedIds: ['a', 'b'],
      currentPageIds: ['page-1'],
      cloudRegionId: 3,
      filters,
      unassignedOnly: false
    });
    expect(result.empty).toBe(false);
    expect(result.query).toEqual({});
    expect(result.body).toEqual({
      cloud_region_id: 3,
      filters
    });
    expect(result.body?.selected_ids).toBeUndefined();
  });

  it('all scope keeps unassigned query and still ignores selected ids', () => {
    const result = buildNodeExportRequest({
      scope: 'all',
      selectedIds: ['a'],
      currentPageIds: ['page-1'],
      cloudRegionId: 3,
      filters,
      unassignedOnly: true
    });
    expect(result.empty).toBe(false);
    expect(result.query).toEqual({ unassigned: true });
    expect(result.body).toEqual({
      cloud_region_id: 3,
      filters
    });
    expect(result.body?.selected_ids).toBeUndefined();
  });

  it('selected scope with no ids is empty and not all', () => {
    const result = buildNodeExportRequest({
      scope: 'selected',
      selectedIds: [],
      currentPageIds: ['page-1'],
      cloudRegionId: 3,
      filters,
      unassignedOnly: false
    });
    expect(result.empty).toBe(true);
    expect(result.body).toBeUndefined();
  });

  it('currentPage scope with no ids is empty and not all', () => {
    const result = buildNodeExportRequest({
      scope: 'currentPage',
      selectedIds: ['a'],
      currentPageIds: [],
      cloudRegionId: 3,
      filters,
      unassignedOnly: false
    });
    expect(result.empty).toBe(true);
    expect(result.body).toBeUndefined();
  });
});

describe('parseContentDispositionFilename', () => {
  it('prefers RFC 5987 filename* over ascii filename', () => {
    const header =
      'attachment; filename="nodes.xlsx"; filename*=UTF-8\'\'%E8%8A%82%E7%82%B9%E6%B8%85%E5%8D%95_region_20260928_120000.xlsx';
    expect(parseContentDispositionFilename(header)).toBe(
      '节点清单_region_20260928_120000.xlsx'
    );
  });

  it('parses a quoted Chinese filename', () => {
    expect(
      parseContentDispositionFilename(
        'attachment; filename="节点清单_默认云区域_20260928_120000.xlsx"'
      )
    ).toBe('节点清单_默认云区域_20260928_120000.xlsx');
  });

  it('returns empty string when the header is missing', () => {
    expect(parseContentDispositionFilename(undefined)).toBe('');
    expect(parseContentDispositionFilename(null)).toBe('');
  });
});

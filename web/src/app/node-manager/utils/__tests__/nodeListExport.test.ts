import { describe, expect, it } from 'vitest';
import {
  buildNodeExportRequest,
  parseContentDispositionFilename
} from '../nodeListExport';

describe('buildNodeExportRequest', () => {
  it('sends selected ids and skips filters', () => {
    const result = buildNodeExportRequest({
      selectedIds: ['a', 'b'],
      cloudRegionId: 3,
      filters: { name: [{ lookup_expr: 'icontains', value: 'x' }] },
      unassignedOnly: true
    });
    expect(result.query).toEqual({ unassigned: true });
    expect(result.body).toEqual({
      cloud_region_id: 3,
      selected_ids: ['a', 'b']
    });
    expect(result.body.filters).toBeUndefined();
  });

  it('sends filters when nothing is selected', () => {
    const filters = { active: [{ lookup_expr: 'in', value: ['false'] }] };
    const result = buildNodeExportRequest({
      selectedIds: [],
      cloudRegionId: 3,
      filters,
      unassignedOnly: false
    });
    expect(result.query).toEqual({});
    expect(result.body).toEqual({
      cloud_region_id: 3,
      filters
    });
    expect(result.body.selected_ids).toBeUndefined();
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

import { describe, expect, it } from 'vitest';
import { buildNodeExportRequest } from '../nodeListExport';

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

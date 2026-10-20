import { describe, expect, it } from 'vitest';
import { INST_UUID_COLUMN_KEY } from '@/app/cmdb/utils/instUuid';
import {
  instanceUuidFilterAttr,
  visibleSearchableFilterAttrs,
} from './searchFilterAttrs';

describe('instance uuid filter', () => {
  const attrs = [
    { attr_id: 'inst_name', attr_type: 'str' },
    instanceUuidFilterAttr('UUID'),
  ];

  it('exposes uuid as a string field named inst_uuid', () => {
    expect(instanceUuidFilterAttr('UUID')).toMatchObject({
      attr_id: INST_UUID_COLUMN_KEY,
      attr_name: 'UUID',
      attr_type: 'str',
    });
  });

  it('includes uuid in the search fields only when the column is displayed', () => {
    expect(visibleSearchableFilterAttrs(attrs, ['inst_name']).map((attr) => attr.attr_id)).toEqual([
      'inst_name',
    ]);
    expect(
      visibleSearchableFilterAttrs(attrs, ['inst_name', INST_UUID_COLUMN_KEY]).map((attr) => attr.attr_id),
    ).toEqual(['inst_name', INST_UUID_COLUMN_KEY]);
  });
});
